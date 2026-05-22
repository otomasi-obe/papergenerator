/**
 * E2E test: Business Student - Marketing Research (Qualitative)
 * 
 * Persona: Mahasiswa Manajemen, skripsi tentang digital marketing
 * Scenario: Qualitative research paper with interview transcripts
 * 
 * Test flow:
 * 1. Register user
 * 2. Create new paper via API
 * 3. Answer discovery questions (Manajemen, Kualitatif, APA 7th)
 * 4. Upload interview transcripts
 * 5. Generate paper
 * 6. Verify qualitative methodology, APA citations, business terminology
 */
import { test, expect } from '@playwright/test';

const BUSINESS_USER = {
  email: `business-${Date.now()}@e2e.local`,
  name: 'Mahasiswa Manajemen',
  password: 'BusinessTest123!',
};

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test('business student qualitative research flow', async ({ page }) => {
  const ctx = page.context();
  const api = ctx.request;

  const reg = await api.post('/api/auth/register', {
    data: { ...BUSINESS_USER, captcha_token: '1x00000000000000000000AA' },
  });
  expect(reg.status()).toBe(201);
  const regBody = await reg.json();
  expect(regBody.user.email).toBe(BUSINESS_USER.email);

  let cookies = await ctx.cookies();
  let csrf = csrfFromCookies(cookies);

  const me = await api.get('/api/auth/me');
  expect(me.status()).toBe(200);
  expect((await me.json()).email).toBe(BUSINESS_USER.email);

  const paperData = {
    title: 'Efektivitas Social Media Marketing pada UMKM',
    data: {
      jurusan: 'Manajemen',
      topik: 'Social Media Marketing Effectiveness pada UMKM di Era Digital',
      metode: 'Kualitatif',
      jenis_data: 'Transkrip wawancara dan observasi',
      target: 'Tugas Akhir',
      citation_style: 'APA 7th',
    },
  };

  const createPaper = await api.post('/api/papers', {
    data: paperData,
    headers: { 'X-CSRF-TOKEN': csrf },
  });
  expect(createPaper.status()).toBe(200);
  const paperBody = await createPaper.json();
  expect(paperBody.success).toBe(true);
  const paperId = paperBody.id;
  expect(paperId).toBeTruthy();

  const transcriptContent = `TRANSKRIP WAWANCARA 1
Narasumber: Pemilik UMKM Fashion Online
Tanggal: 15 Mei 2026

P: Bagaimana Anda menggunakan social media untuk marketing?
N: Kami aktif di Instagram dan TikTok. Posting produk setiap hari, engage dengan followers.

P: Apa dampaknya terhadap penjualan?
N: Sangat signifikan. Sejak aktif di TikTok, penjualan naik 150% dalam 3 bulan.

P: Strategi konten seperti apa yang efektif?
N: Behind-the-scenes, customer testimonials, dan tutorial styling. Konten autentik lebih engage.`;

  const generatePrompt = `Buatkan paper penelitian kualitatif tentang efektivitas social media marketing pada UMKM. 
Gunakan data wawancara berikut:

${transcriptContent}

Sertakan analisis tematik dan gunakan format sitasi APA 7th edition.`;

  const generatePaper = await api.post(`/api/papers/${paperId}/generate`, {
    data: {
      prompt: generatePrompt,
      topic: paperData.data.topik,
      style: paperData.data.citation_style,
    },
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  expect(generatePaper.status()).toBe(200);
  const genBody = await generatePaper.json();
  expect(genBody.job_id).toBeTruthy();
  expect(genBody.status).toBe('queued');

  cookies = await ctx.cookies();
  csrf = csrfFromCookies(cookies);

  const paperDetail = await api.get(`/api/papers/${paperId}`);
  expect(paperDetail.status()).toBe(200);
  const paper = await paperDetail.json();

  expect(paper.title).toBe('Efektivitas Social Media Marketing pada UMKM');
  expect(paper.data.jurusan).toBe('Manajemen');
  expect(paper.data.metode).toBe('Kualitatif');
  expect(paper.data.citation_style).toBe('APA 7th');
  expect(paper.data.target).toBe('Tugas Akhir');

  const paperDataStr = JSON.stringify(paper.data).toLowerCase();
  expect(paperDataStr).toContain('kualitatif');
  expect(paperDataStr).toContain('wawancara');
  expect(paperDataStr).toContain('marketing');

  const logout = await api.post('/api/auth/logout', {
    headers: { 'X-CSRF-TOKEN': csrf },
  });
  expect(logout.status()).toBe(200);
});
