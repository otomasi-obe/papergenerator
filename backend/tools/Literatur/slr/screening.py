"""Active Learning Screening untuk SLR.

SPECTER2 embedding + SVM certainty-based sampling + stopping rule + WSS@95.

Implementasi mengacu pada:
- van de Schoot et al. (2021) "An open source machine learning framework for
  efficient and transparent systematic reviews" — ASReview
- Fu & Wang (2023) "SPECTER2: A General-Purpose Scientific Document Embedding Model"
- Cormack & Grossman (2016) "Scalability of Continuous Active Learning"

Algoritma:
1. Embed semua abstrak dengan SPECTER2 (sekali, di-cache)
2. Mulai dengan seed paper (included) + random sample sebagai training awal
3. Iterasi active learning: SVM → certainty sampling → manusia label
4. Stopping rule: estimasi recall ≥ 95% ATAU N consecutive irrelevant berturut-turut
5. Hitung WSS@95 — proporsi abstrak yang TIDAK perlu dibaca manusia
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

log = logging.getLogger(__name__)

# ── Embedding ──────────────────────────────────────────────────────────────

_SPECTER_MODEL = "allenai/specter2_base"
_SPECTER = None
_SPECTER_ADAPTER = None
_EMBED_DIM = 768


def _get_specter():
    """Lazy-load SPECTER2 via sentence-transformers + adapter.

    SPECTER2_base menghasilkan embedding 768-dimensi yang dioptimalkan
    untuk dokumen ilmiah — menangkap semantik judul + abstrak.
    """
    global _SPECTER, _SPECTER_ADAPTER, _EMBED_DIM
    if _SPECTER is not None:
        return _SPECTER

    try:
        from sentence_transformers import SentenceTransformer

        _SPECTER = SentenceTransformer(_SPECTER_MODEL)
        _SPECTER_ADAPTER = True
        log.info("SPECTER2 loaded: %s (dim=%d)", _SPECTER_MODEL, _EMBED_DIM)
        return _SPECTER
    except Exception:
        log.warning(
            "SPECTER2 unavailable (%s), falling back to all-MiniLM-L6-v2 (384d)",
            _SPECTER_MODEL,
        )
        try:
            from sentence_transformers import SentenceTransformer

            _EMBED_DIM = 384
            _SPECTER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            _SPECTER_ADAPTER = False
            return _SPECTER
        except Exception:
            log.error("No sentence-transformers available — screening disabled")
            return None


def embed_batch(
    texts: list[str],
    batch_size: int = 32,
    show_progress: bool = False,
) -> NDArray | None:
    """Embed list of title+abstract texts into SPECTER2 vectors.

    Args:
        texts: List of strings (title + " " + abstract, truncated to 512 tokens)
        batch_size: Batch size for encoding
        show_progress: Show progress bar

    Returns:
        (N, 768) numpy array, or None if embedding model unavailable
    """
    model = _get_specter()
    if model is None:
        return None

    # Truncate each text to ~4000 chars (~512 tokens)
    truncated = [t[:4000] if t else "" for t in texts]

    embeddings = model.encode(
        truncated,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embeddings  # type: ignore[return-value]


def embed_single(text: str) -> NDArray | None:
    """Embed satu teks."""
    result = embed_batch([text], batch_size=1)
    return result[0] if result is not None else None


# ── Active Learning State ──────────────────────────────────────────────────


@dataclass
class ScreeningState:
    """State screening yang bisa diserialize/disimpan ke JSONB."""

    # Paper IDs + metadata
    paper_ids: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    abstracts: list[str] = field(default_factory=list)

    # Labels: 1 = relevant/included, 0 = irrelevant/excluded
    labels: list[int] = field(default_factory=list)

    # Urutan screening (indices ke paper_ids)
    screened_idx: list[int] = field(default_factory=list)
    unscreened_idx: list[int] = field(default_factory=list)

    # Estimasi recall setelah setiap iterasi
    recall_estimates: list[float] = field(default_factory=list)

    # Statistik
    n_total: int = 0
    n_screened: int = 0
    n_relevant_found: int = 0
    n_irrelevant_found: int = 0
    consecutive_irrelevant: int = 0
    stopped: bool = False
    stop_reason: str = ""

    # Timestamps
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "paper_ids": self.paper_ids,
            "titles": self.titles,
            "abstracts": self.abstracts,
            "labels": self.labels,
            "screened_idx": self.screened_idx,
            "unscreened_idx": self.unscreened_idx,
            "recall_estimates": self.recall_estimates,
            "n_total": self.n_total,
            "n_screened": self.n_screened,
            "n_relevant_found": self.n_relevant_found,
            "n_irrelevant_found": self.n_irrelevant_found,
            "consecutive_irrelevant": self.consecutive_irrelevant,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScreeningState:
        return cls(**{k: d.get(k, v.default if hasattr(v, "default") else v)
                       for k, v in cls.__dataclass_fields__.items()})


@dataclass
class ScreeningResult:
    """Hasil akhir screening."""

    state: ScreeningState

    # Paper IDs yang lolos screening (relevant)
    included_ids: list[str]
    included_titles: list[str]

    # Metrik
    recall_at_stop: float       # estimated recall saat berhenti
    wss95: float                # Work Saved over Sampling at 95% recall
    n_screened: int             # total abstrak yang dibaca manusia
    n_total: int                # total abstrak dalam pool
    n_relevant: int             # total relevant ditemukan
    precision: float            # precision pada titik berhenti
    time_elapsed: float         # detik

    def to_dict(self) -> dict:
        return {
            "included_ids": self.included_ids,
            "included_titles": self.included_titles,
            "recall_at_stop": round(self.recall_at_stop, 4),
            "wss95": round(self.wss95, 4),
            "n_screened": self.n_screened,
            "n_total": self.n_total,
            "n_relevant": self.n_relevant,
            "precision": round(self.precision, 4),
            "time_elapsed": round(self.time_elapsed, 2),
            "stop_reason": self.state.stop_reason,
            "state_summary": {
                "consecutive_irrelevant": self.state.consecutive_irrelevant,
                "recall_estimates": [round(r, 4) for r in self.state.recall_estimates[-5:]],
            },
        }


# ── Stopping Rule ──────────────────────────────────────────────────────────


class StoppingRule:
    """Aturan berhenti screening.

    Dua kriteria (OR):
    1. Estimasi recall ≥ target (default 95%)
    2. N consecutive irrelevant berturut-turut (default 50)

    Estimasi recall menggunakan metode ASReview: jumlah relevant yang ditemukan
    selama screening terakhir dibandingkan dengan estimasi total relevant.
    """

    def __init__(
        self,
        target_recall: float = 0.95,
        max_consecutive_irrelevant: int = 50,
        min_screened: int = 50,
    ):
        self.target_recall = target_recall
        self.max_consecutive_irrelevant = max_consecutive_irrelevant
        self.min_screened = min_screened

    def should_stop(self, state: ScreeningState) -> tuple[bool, str]:
        """Cek apakah screening harus berhenti.

        Returns:
            (should_stop, reason)
        """
        # Belum cukup data untuk estimasi
        if state.n_screened < self.min_screened:
            return False, ""

        # Cek 1: consecutive irrelevant melebihi threshold
        if state.consecutive_irrelevant >= self.max_consecutive_irrelevant:
            return True, (
                f"consecutive_irrelevant={state.consecutive_irrelevant} "
                f"(threshold={self.max_consecutive_irrelevant})"
            )

        # Cek 2: estimasi recall ≥ target
        recall_est = _estimate_recall(state)
        state.recall_estimates.append(recall_est)

        if recall_est >= self.target_recall:
            return True, (
                f"recall_estimate={recall_est:.4f} >= target={self.target_recall}"
            )

        return False, ""


def _estimate_recall(state: ScreeningState) -> float:
    """Estimasi recall menggunakan metode simplifikasi ASReview.

    Berdasarkan proporsi relevant dalam screening terbaru vs total screened.
    Menggunakan moving window dari N screening terakhir untuk stabilitas.

    Formula:
        recall_est = n_relevant_found / (n_relevant_found + estimate_unseen_relevant)

    Dimana estimate_unseen_relevant dihitung dari rate penemuan relevant
    di window terakhir yang diskalakan ke sisa unscreened.
    """
    if state.n_screened == 0 or state.n_relevant_found == 0:
        return 0.0

    window_size = min(100, state.n_screened)
    recent_screened = state.screened_idx[-window_size:]
    recent_relevant = sum(1 for i in recent_screened if state.labels[i] == 1)

    if recent_relevant == 0:
        # Tidak ada relevant di window terbaru → recall sudah tinggi
        # Tapi kita perlu estimasi lebih konservatif
        # Gunakan overall rate
        overall_rate = state.n_relevant_found / state.n_screened
        remaining = state.n_total - state.n_screened
        estimated_unseen = overall_rate * remaining
    else:
        # Relevant masih muncul → ekstrapolasi
        recent_rate = recent_relevant / window_size
        remaining = state.n_total - state.n_screened
        estimated_unseen = recent_rate * remaining

    estimated_total = state.n_relevant_found + estimated_unseen
    if estimated_total == 0:
        return 0.0

    return state.n_relevant_found / estimated_total


# ── WSS@95 ─────────────────────────────────────────────────────────────────


def compute_wss95(state: ScreeningState, true_relevant_count: int | None = None) -> float:
    """Hitung Work Saved over Sampling at 95% recall.

    WSS@95 = proporsi abstrak yang TIDAK perlu dibaca manusia sambil
    tetap menangkap 95% paper relevan.

    Formula:
        WSS@95 = (N_total - N_screened_at_95recall) / N_total

    Dimana N_screened_at_95recall adalah jumlah yang harus discreen
    untuk mencapai recall 95%.

    Args:
        state: State screening (harus sudah selesai)
        true_relevant_count: Jika diketahui (mis. dari expert review),
                            dipakai untuk validasi. Jika None, pakai estimasi.

    Returns:
        WSS@95 score (0.0 - 1.0), lebih tinggi = lebih baik
    """
    if state.n_total == 0:
        return 0.0

    # Cari titik dimana recall pertama kali ≥ 0.95
    if true_relevant_count:
        target = int(0.95 * true_relevant_count)
        relevant_count = 0
        screened_at_target = 0
        for i, idx in enumerate(state.screened_idx, 1):
            if state.labels[idx] == 1:
                relevant_count += 1
            if relevant_count >= target:
                screened_at_target = i
                break
        if screened_at_target == 0:
            screened_at_target = state.n_screened
    else:
        # Estimasi dari recall_estimates
        screened_at_target = state.n_screened
        for i, est in enumerate(state.recall_estimates):
            if est >= 0.95:
                # Recall estimate ke-i dicapai setelah screening ke-(min_screened + i)
                screened_at_target = state.n_total  # akan dikoreksi
                # Hitung dari screened_idx
                min_screened = max(0, state.n_screened - len(state.recall_estimates))
                screened_at_target = min_screened + i + 1
                break

    wss = (state.n_total - screened_at_target) / state.n_total
    return max(0.0, min(1.0, wss))


# ── Active Screener ────────────────────────────────────────────────────────


class ActiveScreener:
    """Active learning screener: SPECTER2 + SVM + certainty sampling.

    Usage:
        screener = ActiveScreener(target_recall=0.95)
        screener.initialize(paper_ids, titles, abstracts, seed_included=[0, 5])

        while not screener.state.stopped:
            next_idx = screener.next_to_screen()
            # ... manusia/Ui memberi label ...
            screener.label(next_idx, is_relevant=True)

        result = screener.finalize()
        print(f"WSS@95: {result.wss95:.2%}")
    """

    def __init__(
        self,
        target_recall: float = 0.95,
        max_consecutive_irrelevant: int = 50,
        min_screened: int = 50,
        svm_kernel: str = "rbf",
        svm_C: float = 1.0,
        random_seed: int = 42,
    ):
        self.stopping_rule = StoppingRule(
            target_recall=target_recall,
            max_consecutive_irrelevant=max_consecutive_irrelevant,
            min_screened=min_screened,
        )
        self.svm_kernel = svm_kernel
        self.svm_C = svm_C
        self.random_seed = random_seed
        self.rng = np.random.RandomState(random_seed)

        self.state: ScreeningState | None = None
        self.embeddings: NDArray | None = None
        self._clf = None
        self._started_at: float = 0.0

    # ── Initialization ─────────────────────────────────────────────────

    def initialize(
        self,
        paper_ids: list[str],
        titles: list[str],
        abstracts: list[str],
        seed_included: list[int] | None = None,
        seed_excluded: list[int] | None = None,
        embeddings: NDArray | None = None,
    ) -> ScreeningState:
        """Inisialisasi screening state.

        Args:
            paper_ids: Unique IDs untuk setiap paper
            titles: Judul paper
            abstracts: Abstrak paper
            seed_included: Indeks paper yang sudah diketahui relevant (seed)
            seed_excluded: Indeks paper yang sudah diketahui irrelevant
            embeddings: Pre-computed embeddings (optional, akan dihitung kalau None)

        Returns:
            ScreeningState — state awal
        """
        n = len(paper_ids)
        self._started_at = time.time()

        state = ScreeningState(
            paper_ids=list(paper_ids),
            titles=list(titles),
            abstracts=list(abstracts),
            labels=[-1] * n,  # -1 = unlabeled
            screened_idx=[],
            unscreened_idx=list(range(n)),
            n_total=n,
            started_at=self._started_at,
        )

        # Seed labels
        seed_included = seed_included or []
        seed_excluded = seed_excluded or []
        for idx in seed_included:
            if 0 <= idx < n:
                state.labels[idx] = 1
        for idx in seed_excluded:
            if 0 <= idx < n and state.labels[idx] == -1:
                state.labels[idx] = 0

        # Hitung embedding kalau belum disediakan
        if embeddings is not None:
            self.embeddings = embeddings
        else:
            texts = [
                (titles[i] or "") + " " + (abstracts[i] or "")
                for i in range(n)
            ]
            self.embeddings = embed_batch(texts)

        if self.embeddings is None:
            raise RuntimeError(
                "SPECTER2 embedding gagal — pastikan sentence-transformers terinstall"
            )

        # Pastikan embedding punya akses memori contiguous
        self.embeddings = np.ascontiguousarray(self.embeddings, dtype=np.float32)

        # Update screened/unscreened berdasarkan seed
        seed_all = set(seed_included) | set(seed_excluded)
        for idx in sorted(seed_all):
            if idx in state.unscreened_idx:
                state.unscreened_idx.remove(idx)
                state.screened_idx.append(idx)
                state.n_screened += 1
                if state.labels[idx] == 1:
                    state.n_relevant_found += 1
                else:
                    state.n_irrelevant_found += 1

        self.state = state

        # Latih classifier awal
        self._train_classifier()

        log.info(
            "Screening initialized: %d papers, %d seed, %d unlabeled",
            n, len(seed_all), len(state.unscreened_idx),
        )
        return state

    # ── Active Learning Loop ───────────────────────────────────────────

    def next_to_screen(self) -> int | None:
        """Return indeks paper berikutnya untuk discreen (certainty sampling).

        Pilih paper yang classifier-nya PALING TIDAK YAKIN
        (probabilitas relevan terdekat ke 0.5).

        Returns:
            Indeks ke paper_ids, atau None kalau semua sudah discreen.
        """
        if self.state is None:
            raise RuntimeError("Screener belum di-inisialisasi — panggil initialize() dulu")

        if not self.state.unscreened_idx:
            return None

        if self._clf is None:
            # Belum ada classifier — random sampling
            idx = int(self.rng.choice(self.state.unscreened_idx))
            return idx

        # Certainty sampling: pilih yang paling uncertainty
        unscreened = np.array(self.state.unscreened_idx)
        X = self.embeddings[unscreened]  # type: ignore[index]

        try:
            proba = self._clf.predict_proba(X)
            # proba[:, 1] = P(relevant)
            # uncertainty = 1 - |P(relevant) - 0.5| * 2 → 0 = most uncertain
            uncertainty = 1.0 - np.abs(proba[:, 1] - 0.5) * 2.0
            most_uncertain = unscreened[int(np.argmax(uncertainty))]
            return int(most_uncertain)

        except Exception:
            # Fallback: random
            return int(self.rng.choice(self.state.unscreened_idx))

    def label(self, idx: int, is_relevant: bool) -> None:
        """Beri label pada paper yang sudah discreen.

        Args:
            idx: Indeks ke paper_ids
            is_relevant: True = relevant/included, False = irrelevant/excluded
        """
        if self.state is None:
            raise RuntimeError("Screener belum di-inisialisasi")

        if idx not in self.state.unscreened_idx:
            log.warning("Paper %d sudah discreen sebelumnya", idx)
            return

        # Update state
        self.state.unscreened_idx.remove(idx)
        self.state.screened_idx.append(idx)
        self.state.n_screened += 1
        self.state.labels[idx] = 1 if is_relevant else 0

        if is_relevant:
            self.state.n_relevant_found += 1
            self.state.consecutive_irrelevant = 0
        else:
            self.state.n_irrelevant_found += 1
            self.state.consecutive_irrelevant += 1

        # Re-train classifier (incremental kalau mungkin)
        self._train_classifier()

    def label_batch(self, pairs: list[tuple[int, bool]]) -> None:
        """Batch labeling — lebih efisien untuk UI yang mendukung batch review."""
        for idx, is_relevant in pairs:
            if idx in (self.state.unscreened_idx if self.state else []):
                self.label(idx, is_relevant)

    def check_stop(self) -> tuple[bool, str]:
        """Cek apakah stopping rule terpenuhi."""
        if self.state is None:
            return False, ""
        should_stop, reason = self.stopping_rule.should_stop(self.state)
        if should_stop:
            self.state.stopped = True
            self.state.stop_reason = reason
            self.state.finished_at = time.time()
        return should_stop, reason

    # ── Finalization ───────────────────────────────────────────────────

    def finalize(self, true_relevant_count: int | None = None) -> ScreeningResult:
        """Finalisasi screening — hitung metrik dan kembalikan hasil.

        Args:
            true_relevant_count: Jika diketahui dari expert (untuk validasi WSS@95)

        Returns:
            ScreeningResult dengan semua metrik
        """
        if self.state is None:
            raise RuntimeError("Screener belum di-inisialisasi")

        # Mark sebagai stopped kalau belum
        if not self.state.stopped:
            self.state.stopped = True
            self.state.stop_reason = "all_screened"
            self.state.finished_at = time.time()

        # Hitung metrik
        included_ids = []
        included_titles = []
        for idx in self.state.screened_idx:
            if self.state.labels[idx] == 1:
                included_ids.append(self.state.paper_ids[idx])
                included_titles.append(self.state.titles[idx])

        recall_at_stop = (
            self.state.recall_estimates[-1]
            if self.state.recall_estimates
            else _estimate_recall(self.state)
        )

        wss95 = compute_wss95(self.state, true_relevant_count)

        precision = (
            self.state.n_relevant_found / self.state.n_screened
            if self.state.n_screened > 0
            else 0.0
        )

        time_elapsed = self.state.finished_at - self.state.started_at

        result = ScreeningResult(
            state=self.state,
            included_ids=included_ids,
            included_titles=included_titles,
            recall_at_stop=recall_at_stop,
            wss95=wss95,
            n_screened=self.state.n_screened,
            n_total=self.state.n_total,
            n_relevant=self.state.n_relevant_found,
            precision=precision,
            time_elapsed=time_elapsed,
        )

        log.info(
            "Screening final: %d/%d screened, %d relevant, "
            "WSS@95=%.2%%, recall=%.2%%, precision=%.2%%, "
            "time=%.1fs, stop=%s",
            result.n_screened, result.n_total, result.n_relevant,
            result.wss95, result.recall_at_stop, result.precision,
            result.time_elapsed, self.state.stop_reason,
        )

        return result

    # ── Internal ───────────────────────────────────────────────────────

    def _train_classifier(self) -> None:
        """Latih SVM classifier dari data labeled saat ini."""
        if self.state is None or self.embeddings is None:
            return

        labeled_idx = [
            i for i in range(self.state.n_total)
            if self.state.labels[i] in (0, 1)
        ]
        if len(labeled_idx) < 2:
            self._clf = None
            return

        # Cek apakah ada kedua kelas
        unique_labels = {self.state.labels[i] for i in labeled_idx}
        if len(unique_labels) < 2:
            self._clf = None
            return

        X_train = self.embeddings[labeled_idx]
        y_train = np.array([self.state.labels[i] for i in labeled_idx])

        # Class weight untuk handle imbalance
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.svm import SVC

        n_relevant = int(np.sum(y_train == 1))
        n_irrelevant = int(np.sum(y_train == 0))

        if n_relevant == 0 or n_irrelevant == 0:
            self._clf = None
            return

        class_weight = {0: 1.0, 1: max(1.0, n_irrelevant / max(n_relevant, 1))}

        base_svc = SVC(
            kernel=self.svm_kernel,
            C=self.svm_C,
            class_weight=class_weight,
            random_state=self.random_seed,
            cache_size=500,
        )
        self._clf = CalibratedClassifierCV(base_svc, method='sigmoid', cv=3)
        self._clf.fit(X_train, y_train)

    def get_scores(self) -> dict[int, float]:
        """Return relevance probability untuk semua unscreened papers.

        Returns:
            Dict[index → P(relevant)]
        """
        if self.state is None or self._clf is None or self.embeddings is None:
            return {}

        unscreened = np.array(self.state.unscreened_idx)
        if len(unscreened) == 0:
            return {}

        X = self.embeddings[unscreened]
        try:
            proba = self._clf.predict_proba(X)
            return {int(idx): float(proba[i, 1]) for i, idx in enumerate(unscreened)}
        except Exception:
            return {}

    def get_top_k(self, k: int = 10) -> list[tuple[int, float]]:
        """Return top-K unscreened papers ranked by relevance probability.

        Returns:
            List of (index, probability) sorted descending
        """
        scores = self.get_scores()
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:k]


# ── Utility ────────────────────────────────────────────────────────────────


def run_screening(
    paper_ids: list[str],
    titles: list[str],
    abstracts: list[str],
    labels: list[int] | None = None,
    seed_ratio: float = 0.05,
    target_recall: float = 0.95,
    max_consecutive_irrelevant: int = 50,
    random_seed: int = 42,
) -> ScreeningResult:
    """Jalankan screening loop penuh secara otomatis (untuk testing/benchmark).

    Kalau `labels` disediakan, ini adalah simulasi dengan ground truth.
    Kalau tidak, ini adalah screening tanpa label — hanya menghasilkan urutan.

    Args:
        paper_ids: Unique IDs
        titles: Judul
        abstracts: Abstrak
        labels: Ground truth labels (1=relevant, 0=irrelevant, -1=unknown)
        seed_ratio: Proporsi data untuk seed (0.05 = 5%)
        target_recall: Target recall untuk stopping
        max_consecutive_irrelevant: Threshold consecutive irrelevant
        random_seed: Random seed

    Returns:
        ScreeningResult dengan semua metrik
    """
    rng = np.random.RandomState(random_seed)
    n = len(paper_ids)

    if labels is None:
        labels = [-1] * n

    # Buat seed: 1 relevant + 1 irrelevant (kalau ada)
    relevant_idx = [i for i, l in enumerate(labels) if l == 1]
    irrelevant_idx = [i for i, l in enumerate(labels) if l == 0]

    seed_included = []
    seed_excluded = []

    if relevant_idx:
        seed_included.append(int(rng.choice(relevant_idx)))
    if irrelevant_idx:
        seed_excluded.append(int(rng.choice(irrelevant_idx)))

    # Tambah random seed kalau kurang
    n_seed = max(2, int(n * seed_ratio))
    while len(seed_included) + len(seed_excluded) < n_seed:
        rand_idx = int(rng.randint(0, n))
        if rand_idx not in seed_included and rand_idx not in seed_excluded:
            if labels[rand_idx] == 1:
                seed_included.append(rand_idx)
            elif labels[rand_idx] == 0:
                seed_excluded.append(rand_idx)

    screener = ActiveScreener(
        target_recall=target_recall,
        max_consecutive_irrelevant=max_consecutive_irrelevant,
        random_seed=random_seed,
    )
    screener.initialize(
        paper_ids, titles, abstracts,
        seed_included=seed_included,
        seed_excluded=seed_excluded,
    )

    # Screening loop
    while True:
        next_idx = screener.next_to_screen()
        if next_idx is None:
            break

        screener.label(next_idx, labels[next_idx] == 1)

        should_stop, reason = screener.check_stop()
        if should_stop:
            break

    true_relevant = sum(1 for l in labels if l == 1)
    return screener.finalize(true_relevant_count=true_relevant)


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Data sintetis: 500 paper, 50 relevant (10%)
    n_total = 500
    n_relevant = 50
    rng = np.random.RandomState(42)

    paper_ids = [f"paper_{i:04d}" for i in range(n_total)]
    titles = [f"Research on topic {i}: novel approach to systematic review" for i in range(n_total)]
    abstracts = [f"Abstract {i} discussing machine learning for SLR automation" for i in range(n_total)]

    # Buat beberapa "relevant" dengan judul lebih spesifik
    labels = [0] * n_total
    relevant_positions = rng.choice(n_total, n_relevant, replace=False)
    for pos in relevant_positions:
        labels[pos] = 1
        titles[pos] = f"IMPORTANT: Deep learning for automated SLR screening {pos}"
        abstracts[pos] = f"Key paper on active learning and systematic review automation {pos}"

    print(f"Running screening: {n_total} papers, {n_relevant} relevant")
    result = run_screening(
        paper_ids, titles, abstracts, labels,
        seed_ratio=0.02,
        target_recall=0.95,
    )

    print(f"\n{'='*60}")
    print(f"SCREENING RESULT")
    print(f"{'='*60}")
    print(f"Total papers:           {result.n_total}")
    print(f"Screened:               {result.n_screened} ({result.n_screened/result.n_total:.1%})")
    print(f"Relevant found:         {result.n_relevant}")
    print(f"Precision:              {result.precision:.2%}")
    print(f"Recall at stop:         {result.recall_at_stop:.2%}")
    print(f"WSS@95:                 {result.wss95:.2%}")
    print(f"Time elapsed:           {result.time_elapsed:.1f}s")
    print(f"Stop reason:            {result.stop_reason}")
    print(f"Included papers:        {len(result.included_ids)}")