/**
 * E2E test: Medical Student - Clinical Research
 * 
 * Persona: Mahasiswa Kedokteran, penelitian klinis tentang diabetes management
 * Test Scenario: Literature review paper with medical terminology
 * 
 * Flow:
 * 1. Register medical student user
 * 2. Create new paper with medical research parameters
 * 3. Answer discovery questions (Kedokteran, Diabetes Management, Literature Review)
 * 4. Run SLR with medical databases
 * 5. Verify medical terminology accuracy
 * 6. Check Vancouver citation format
 * 7. Verify ethical considerations mentioned
 * 8. Check for proper medical abbreviations
 */
import { test, expect } from '@playwright/test';

const MEDICAL_USER = {
  email: 'medical-e2e@test.local',
  name: 'Dr. Medical Student',
  password: 'MedicalPass123!',
};

const MEDICAL_PAPER_DATA = {
  title: 'Diabetes Management with Mobile Health Apps: A Systematic Literature Review',
  discovery: {
    jurusan: 'Kedokteran',
    topik: 'Diabetes Management with Mobile Health Apps',
    jenis: 'Literature Review / Systematic Review',
    target: 'Jurnal internasional',
    citation_style: 'Vancouver',
    research_question: 'How effective are mobile health applications in improving diabetes management outcomes?',
    keywords: ['diabetes mellitus', 'mobile health', 'mHealth', 'glycemic control', 'HbA1c', 'self-management'],
  },
};

const MEDICAL_TERMS = [
  'diabetes mellitus',
  'glycemic control',
  'HbA1c',
  'insulin',
  'glucose',
  'hyperglycemia',
  'hypoglycemia',
  'endocrine',
  'metabolic',
  'cardiovascular',
];

const MEDICAL_ABBREVIATIONS = [
  'HbA1c',
  'BMI',
  'WHO',
  'RCT',
  'CI',
  'OR',
  'RR',
  'SD',
  'PRISMA',
];

const ETHICAL_KEYWORDS = [
  'ethical',
  'ethics',
  'informed consent',
  'IRB',
  'ethical approval',
  'ethical considerations',
  'patient privacy',
  'confidentiality',
];

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function waitForJobCompletion(api, jobId, maxWaitMs = 120000, pollIntervalMs = 2000) {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    const resp = await api.get(`/api/slr/jobs/${jobId}`);
    if (resp.status() !== 200) {
      throw new Error(`Job status check failed: ${resp.status()}`);
    }
    const body = await resp.json();
    if (body.status === 'done') {
      return body;
    }
    if (body.status === 'error' || body.status === 'cancelled') {
      throw new Error(`Job failed with status: ${body.status}`);
    }
    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }
  throw new Error('Job did not complete within timeout');
}

test.describe('Medical Student - Clinical Research E2E', () => {
  let userId;
  let paperId;
  let cookies;
  let ctx;
  let api;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    ctx = page.context();
    api = ctx.request;

    let authResp = await api.post('/api/auth/login', {
      data: { email: MEDICAL_USER.email, password: MEDICAL_USER.password },
    });

    if (authResp.status() === 401) {
      const reg = await api.post('/api/auth/register', {
        data: { ...MEDICAL_USER, captcha_token: '1x00000000000000000000AA' },
      });
      
      if (reg.status() === 429) {
        console.log('Rate limit hit, waiting 65 seconds...');
        await new Promise(resolve => setTimeout(resolve, 65000));
        const retryReg = await api.post('/api/auth/register', {
          data: { ...MEDICAL_USER, captcha_token: '1x00000000000000000000AA' },
        });
        expect(retryReg.status()).toBe(201);
        authResp = retryReg;
      } else {
        expect(reg.status()).toBe(201);
        authResp = reg;
      }
    } else {
      expect(authResp.status()).toBe(200);
    }

    const authBody = await authResp.json();
    userId = authBody.user?.id || authBody.id;
    expect(authBody.user?.email || authBody.email).toBe(MEDICAL_USER.email);

    cookies = await ctx.cookies();
    const names = cookies.map((c) => c.name);
    expect(names).toContain('access_token_cookie');
    expect(names).toContain('csrf_access_token');

    await page.close();
  });

  test('1. Create medical research paper', async () => {
    const paperData = {
      title: MEDICAL_PAPER_DATA.title,
      data: {
        title: MEDICAL_PAPER_DATA.title,
        discovery: MEDICAL_PAPER_DATA.discovery,
        metadata: {
          field: 'Medicine',
          subfield: 'Endocrinology',
          research_type: 'Systematic Literature Review',
          target_journal: 'International',
        },
      },
    };

    const resp = await api.post('/api/papers', {
      data: paperData,
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
    });

    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.success).toBe(true);
    expect(body.id).toBeTruthy();
    paperId = body.id;

    const loadResp = await api.get(`/api/papers/${paperId}`);
    expect(loadResp.status()).toBe(200);
    const loadedPaper = await loadResp.json();
    expect(loadedPaper.title).toBe(MEDICAL_PAPER_DATA.title);
    expect(loadedPaper.discovery.jurusan).toBe('Kedokteran');
  });

  test('2. Trigger SLR job with medical query', async () => {
    expect(paperId).toBeTruthy();

    const slrPayload = {
      query: 'diabetes management mobile health apps mHealth glycemic control HbA1c',
      top_k: 50,
      databases: ['pubmed', 'google_scholar', 'semantic_scholar'],
      filters: {
        year_min: 2018,
        year_max: 2026,
        study_types: ['RCT', 'systematic review', 'meta-analysis', 'cohort study'],
      },
    };

    const resp = await api.post(`/api/papers/${paperId}/slr/jobs`, {
      data: slrPayload,
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
    });

    expect(resp.status()).toBe(202);
    const body = await resp.json();
    expect(body.id).toBeTruthy();
    expect(body.status).toBe('queued');
  });

  test('3. Wait for SLR completion and retrieve results', async () => {
    const jobsResp = await api.get(`/api/papers/${paperId}/slr/jobs`);
    expect(jobsResp.status()).toBe(200);
    const jobsBody = await jobsResp.json();
    expect(jobsBody.jobs).toBeTruthy();
    expect(jobsBody.jobs.length).toBeGreaterThan(0);

    const latestJob = jobsBody.jobs[0];
    const jobId = latestJob.id;

    let jobResult;
    try {
      jobResult = await waitForJobCompletion(api, jobId, 180000, 3000);
    } catch (error) {
      console.error('SLR job failed or timed out:', error.message);
      const statusResp = await api.get(`/api/slr/jobs/${jobId}`);
      const statusBody = await statusResp.json();
      console.error('Final job status:', statusBody);
      throw error;
    }

    expect(jobResult.status).toBe('done');
    expect(jobResult.result).toBeTruthy();
  });

  test('4. Verify medical terminology in literature results', async () => {
    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    expect(litResp.status()).toBe(200);
    const litBody = await litResp.json();
    expect(litBody.items).toBeTruthy();
    expect(litBody.items.length).toBeGreaterThan(0);

    const allText = litBody.items
      .map(item => `${item.title || ''} ${item.abstract || ''} ${item.authors || ''}`)
      .join(' ')
      .toLowerCase();

    const foundTerms = MEDICAL_TERMS.filter(term => 
      allText.includes(term.toLowerCase())
    );

    expect(foundTerms.length).toBeGreaterThan(3);
    console.log('Found medical terms:', foundTerms);
  });

  test('5. Verify Vancouver citation format', async () => {
    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    const litBody = await litResp.json();

    const vancouverPatterns = [
      /\d+\.\s+[A-Z]/,
      /\bet al\b/i,
      /\d{4};/,
      /\d+\(\d+\):/,
      /:\d+-\d+\./,
    ];

    let hasVancouverFormat = false;
    for (const item of litBody.items) {
      const citation = item.citation || item.formatted_citation || '';
      if (citation) {
        const matchCount = vancouverPatterns.filter(pattern => 
          pattern.test(citation)
        ).length;
        if (matchCount >= 2) {
          hasVancouverFormat = true;
          console.log('Vancouver format detected in:', citation.substring(0, 100));
          break;
        }
      }
    }

    expect(hasVancouverFormat).toBe(true);
  });

  test('6. Verify medical abbreviations are present', async () => {
    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    const litBody = await litResp.json();

    const allText = litBody.items
      .map(item => `${item.title || ''} ${item.abstract || ''}`)
      .join(' ');

    const foundAbbreviations = MEDICAL_ABBREVIATIONS.filter(abbr => 
      new RegExp(`\\b${abbr}\\b`).test(allText)
    );

    expect(foundAbbreviations.length).toBeGreaterThan(2);
    console.log('Found medical abbreviations:', foundAbbreviations);
  });

  test('7. Verify ethical considerations mentioned', async () => {
    const paperResp = await api.get(`/api/papers/${paperId}`);
    const paperBody = await paperResp.json();

    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    const litBody = await litResp.json();

    const paperText = JSON.stringify(paperBody).toLowerCase();
    const litText = litBody.items
      .map(item => `${item.title || ''} ${item.abstract || ''}`)
      .join(' ')
      .toLowerCase();

    const combinedText = paperText + ' ' + litText;

    const foundEthicalKeywords = ETHICAL_KEYWORDS.filter(keyword => 
      combinedText.includes(keyword.toLowerCase())
    );

    expect(foundEthicalKeywords.length).toBeGreaterThan(0);
    console.log('Found ethical keywords:', foundEthicalKeywords);
  });

  test('8. Verify clinical trial references', async () => {
    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    const litBody = await litResp.json();

    const clinicalTrialPatterns = [
      /randomized controlled trial/i,
      /\bRCT\b/,
      /clinical trial/i,
      /double-blind/i,
      /placebo-controlled/i,
      /intervention study/i,
    ];

    const allText = litBody.items
      .map(item => `${item.title || ''} ${item.abstract || ''} ${item.study_type || ''}`)
      .join(' ');

    const foundPatterns = clinicalTrialPatterns.filter(pattern => 
      pattern.test(allText)
    );

    expect(foundPatterns.length).toBeGreaterThan(0);
    console.log('Found clinical trial patterns:', foundPatterns.length);
  });

  test('9. Generate validation report', async () => {
    const litResp = await api.get(`/api/papers/${paperId}/literature`);
    const litBody = await litResp.json();

    const report = {
      paper_id: paperId,
      paper_title: MEDICAL_PAPER_DATA.title,
      total_literature_items: litBody.items.length,
      validation_results: {
        medical_terminology: {
          checked: MEDICAL_TERMS.length,
          found: MEDICAL_TERMS.filter(term => 
            litBody.items.some(item => 
              `${item.title} ${item.abstract}`.toLowerCase().includes(term.toLowerCase())
            )
          ).length,
        },
        medical_abbreviations: {
          checked: MEDICAL_ABBREVIATIONS.length,
          found: MEDICAL_ABBREVIATIONS.filter(abbr => 
            litBody.items.some(item => 
              new RegExp(`\\b${abbr}\\b`).test(`${item.title} ${item.abstract}`)
            )
          ).length,
        },
        ethical_considerations: {
          checked: ETHICAL_KEYWORDS.length,
          found: ETHICAL_KEYWORDS.filter(keyword => 
            litBody.items.some(item => 
              `${item.title} ${item.abstract}`.toLowerCase().includes(keyword.toLowerCase())
            )
          ).length,
        },
        citation_format: 'Vancouver',
        field: 'Medicine - Endocrinology',
        research_type: 'Systematic Literature Review',
      },
      timestamp: new Date().toISOString(),
    };

    console.log('\n=== MEDICAL STUDENT E2E TEST REPORT ===');
    console.log(JSON.stringify(report, null, 2));
    console.log('========================================\n');

    expect(report.total_literature_items).toBeGreaterThan(0);
    expect(report.validation_results.medical_terminology.found).toBeGreaterThan(0);
  });
});
