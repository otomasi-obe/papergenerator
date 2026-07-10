import { expect, Page, test } from '@playwright/test'

const paperId = 'test-paper-1'
const jobId = 'slr_test123'

async function mockApi(page: Page) {
  let literature = []
  await page.addInitScript(() => {
    localStorage.setItem('pg_user', JSON.stringify({ id: '1', email: 'literature-test@example.com', name: 'Literature Tester', role: 'user', preferred_language: 'id' }))
  })
  await page.addInitScript(({ jobId }) => {
    class MockEventSource extends EventTarget {
      url: string
      onerror: null | (() => void) = null
      constructor(url: string) {
        super()
        this.url = url
        setTimeout(() => this.dispatchEvent(new MessageEvent('snapshot', { data: JSON.stringify({ status: 'running', stage: 'fetching', percent: 15, papers_count: 0 }) })), 100)
        setTimeout(() => this.dispatchEvent(new MessageEvent('partial', { data: JSON.stringify({ event_type: 'partial', job_id: jobId, papers_count: 1, new_papers: [{ id: -1, title: 'AGV Line Follower Robot Navigation', authors: ['Test Author'], year: 2025, source: 'arxiv', abstract: 'A test abstract for AGV line follower robots.' }] }) })), 500)
        setTimeout(() => this.dispatchEvent(new MessageEvent('progress', { data: JSON.stringify({ job_id: jobId, status: 'running', stage: 'summarizing', progress_pct: 80, stage_detail: 'Summarizing with AI', papers_fetched: 1 }) })), 900)
        setTimeout(() => this.dispatchEvent(new MessageEvent('done', { data: JSON.stringify({ status: 'done' }) })), 1300)
      }
      close() {}
    }
    // @ts-expect-error test double
    window.EventSource = MockEventSource
  }, { jobId })

  await page.route(/https?:\/\/[^/]+\/api\/.*/, async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()

    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: '1', email: 'literature-test@example.com', name: 'Literature Tester', role: 'user', preferred_language: 'id' } })
    }
    if (path === `/api/papers/${paperId}`) {
      return route.fulfill({ json: { id: paperId, title: 'Robot AGV Test Paper', abstract: 'Editor paper fixture.', sections: [] } })
    }
    if (path === `/api/papers/${paperId}/images`) return route.fulfill({ json: { images: [] } })
    if (path === `/api/papers/${paperId}/charts`) return route.fulfill({ json: { charts: [] } })
    if (path === `/api/papers/${paperId}/user-state`) return route.fulfill({ json: {} })
    if (path === `/api/papers/${paperId}/slr/jobs/wait`) return route.fulfill({ json: { jobs: [] } })
    if (path === `/api/papers/${paperId}/slr/jobs`) {
      if (method === 'POST') {
        const body = route.request().postDataJSON()
        expect(body.query).toBe('arxiv:robot agv arxiv:line follower scopus:robot agv scholar:robot agv')
        literature = [{ id: 101, title: 'AGV Line Follower Robot Navigation', authors: ['Test Author'], year: 2025, source: 'arxiv', abstract: 'A test abstract for AGV line follower robots.', summary: 'Relevant review from AI reranking.' }]
        return route.fulfill({ status: 202, json: { id: jobId, job_id: jobId, status: 'started' } })
      }
      return route.fulfill({ json: { jobs: [{ id: jobId, status: 'running', stage: 'fetching', progress: 20, queued_at: new Date().toISOString() }] } })
    }
    if (path === `/api/slr/jobs/${jobId}`) return route.fulfill({ json: { id: jobId, status: 'done', progress: 100 } })
    if (path === `/api/papers/${paperId}/literature`) return route.fulfill({ json: { items: literature } })

    return route.fulfill({ json: {} })
  })
}

test('Literatur SLR streams partial paper then shows summarized result', async ({ page }) => {
  await mockApi(page)
  await page.goto(`/editor/${paperId}?panel=literature`)

  await expect(page.getByRole('heading', { name: /Literatur/ })).toBeVisible()
  await page.getByPlaceholder(/Ketik topik/).fill('arxiv:robot agv arxiv:line follower scopus:robot agv scholar:robot agv')
  await page.getByRole('button', { name: 'Jalankan SLR', exact: true }).click()

  await expect(page.getByText('AGV Line Follower Robot Navigation')).toBeVisible()
  await expect(page.getByText('Relevant review from AI reranking.')).toBeVisible()
})
