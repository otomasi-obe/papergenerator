#!/usr/bin/env node
/**
 * Chaos Test Runner with Result Analysis
 * 
 * Runs chaos tests and generates comprehensive reports:
 * - Error handling assessment
 * - Security vulnerability report
 * - Recovery mechanism evaluation
 * - Robustness score
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

const execAsync = promisify(exec);

const REPORT_DIR = './chaos-reports';
const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '-');

const TEST_CATEGORIES = {
  network: {
    name: 'Network Failure Scenarios',
    weight: 0.25,
    tests: ['offline', 'slow network', 'intermittent', 'recovers']
  },
  input: {
    name: 'Invalid Input Scenarios',
    weight: 0.20,
    tests: ['empty form', 'long text', 'special characters', 'SQL injection', 'XSS', 'email format']
  },
  resources: {
    name: 'Resource Exhaustion Scenarios',
    weight: 0.15,
    tests: ['oversized file', 'excessive literature', 'long paper', 'rate limits']
  },
  timeout: {
    name: 'Timeout & Cancellation Scenarios',
    weight: 0.15,
    tests: ['timeout', 'cancellation', 'refresh', 'unsaved changes']
  },
  auth: {
    name: 'Authentication Error Scenarios',
    weight: 0.15,
    tests: ['expired token', 'invalid token', 'logout', 'concurrent session', 'CSRF']
  },
  compatibility: {
    name: 'Browser Compatibility & Edge Cases',
    weight: 0.05,
    tests: ['JavaScript', 'cookies', 'localStorage', 'mobile', 'small viewport', '4K']
  },
  integrity: {
    name: 'Data Integrity & Recovery',
    weight: 0.05,
    tests: ['duplicate', 'consistency', 'corruption']
  }
};

async function runChaosTests() {
  console.log('🔥 Starting Chaos Testing Suite...\n');
  
  try {
    const { stdout, stderr } = await execAsync('npx playwright test chaos.spec.js --reporter=json', {
      cwd: process.cwd(),
      maxBuffer: 10 * 1024 * 1024
    });
    
    return { success: true, output: stdout, error: stderr };
  } catch (error) {
    return { success: false, output: error.stdout, error: error.stderr };
  }
}

function parseTestResults(output) {
  try {
    const jsonMatch = output.match(/\{[\s\S]*"suites"[\s\S]*\}/);
    if (!jsonMatch) {
      console.warn('⚠️  Could not parse JSON output, checking for results file...');
      
      const resultsPath = join(process.cwd(), 'test-results.json');
      if (existsSync(resultsPath)) {
        return JSON.parse(readFileSync(resultsPath, 'utf-8'));
      }
      return null;
    }
    
    return JSON.parse(jsonMatch[0]);
  } catch (error) {
    console.error('❌ Failed to parse test results:', error.message);
    return null;
  }
}

function analyzeResults(results) {
  if (!results || !results.suites) {
    return {
      total: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      categories: {}
    };
  }
  
  const analysis = {
    total: 0,
    passed: 0,
    failed: 0,
    skipped: 0,
    categories: {}
  };
  
  results.suites.forEach(suite => {
    const categoryKey = Object.keys(TEST_CATEGORIES).find(key => 
      suite.title.includes(TEST_CATEGORIES[key].name)
    );
    
    if (!categoryKey) return;
    
    if (!analysis.categories[categoryKey]) {
      analysis.categories[categoryKey] = {
        name: TEST_CATEGORIES[categoryKey].name,
        weight: TEST_CATEGORIES[categoryKey].weight,
        passed: 0,
        failed: 0,
        skipped: 0,
        total: 0,
        tests: []
      };
    }
    
    suite.specs?.forEach(spec => {
      analysis.total++;
      analysis.categories[categoryKey].total++;
      
      const testResult = {
        title: spec.title,
        status: spec.ok ? 'passed' : 'failed',
        duration: spec.tests?.[0]?.results?.[0]?.duration || 0,
        error: spec.tests?.[0]?.results?.[0]?.error?.message || null
      };
      
      if (spec.ok) {
        analysis.passed++;
        analysis.categories[categoryKey].passed++;
      } else {
        analysis.failed++;
        analysis.categories[categoryKey].failed++;
      }
      
      analysis.categories[categoryKey].tests.push(testResult);
    });
  });
  
  return analysis;
}

function calculateRobustnessScore(analysis) {
  let totalScore = 0;
  
  Object.keys(analysis.categories).forEach(key => {
    const category = analysis.categories[key];
    const categoryScore = category.total > 0 
      ? (category.passed / category.total) * 100 
      : 0;
    
    totalScore += categoryScore * category.weight;
  });
  
  return Math.round(totalScore * 100) / 100;
}

function generateErrorHandlingReport(analysis) {
  const report = {
    title: 'Error Handling Assessment',
    timestamp: new Date().toISOString(),
    summary: {},
    details: []
  };
  
  const errorCategories = ['network', 'input', 'timeout', 'auth'];
  
  errorCategories.forEach(key => {
    const category = analysis.categories[key];
    if (!category) return;
    
    const score = category.total > 0 
      ? Math.round((category.passed / category.total) * 100) 
      : 0;
    
    report.summary[category.name] = {
      score: `${score}%`,
      passed: category.passed,
      failed: category.failed,
      total: category.total
    };
    
    category.tests.forEach(test => {
      if (test.status === 'failed') {
        report.details.push({
          category: category.name,
          test: test.title,
          error: test.error,
          recommendation: getErrorRecommendation(test.title, test.error)
        });
      }
    });
  });
  
  return report;
}

function generateSecurityReport(analysis) {
  const report = {
    title: 'Security Vulnerability Report',
    timestamp: new Date().toISOString(),
    vulnerabilities: [],
    passed: [],
    risk_level: 'LOW'
  };
  
  const securityTests = analysis.categories.input?.tests || [];
  
  securityTests.forEach(test => {
    const isSecurity = test.title.toLowerCase().includes('sql') ||
                       test.title.toLowerCase().includes('xss') ||
                       test.title.toLowerCase().includes('injection') ||
                       test.title.toLowerCase().includes('csrf');
    
    if (!isSecurity) return;
    
    if (test.status === 'failed') {
      const severity = test.title.toLowerCase().includes('sql') || 
                       test.title.toLowerCase().includes('xss') 
        ? 'CRITICAL' 
        : 'HIGH';
      
      report.vulnerabilities.push({
        test: test.title,
        severity: severity,
        error: test.error,
        impact: getSecurityImpact(test.title),
        mitigation: getSecurityMitigation(test.title)
      });
      
      if (severity === 'CRITICAL') {
        report.risk_level = 'CRITICAL';
      } else if (severity === 'HIGH' && report.risk_level !== 'CRITICAL') {
        report.risk_level = 'HIGH';
      }
    } else {
      report.passed.push(test.title);
    }
  });
  
  return report;
}

function generateRecoveryReport(analysis) {
  const report = {
    title: 'Recovery Mechanism Evaluation',
    timestamp: new Date().toISOString(),
    mechanisms: {},
    score: 0
  };
  
  const recoveryCategories = ['network', 'timeout', 'integrity'];
  let totalTests = 0;
  let passedTests = 0;
  
  recoveryCategories.forEach(key => {
    const category = analysis.categories[key];
    if (!category) return;
    
    totalTests += category.total;
    passedTests += category.passed;
    
    report.mechanisms[category.name] = {
      status: category.passed === category.total ? 'EXCELLENT' :
              category.passed / category.total > 0.7 ? 'GOOD' :
              category.passed / category.total > 0.5 ? 'FAIR' : 'POOR',
      passed: category.passed,
      total: category.total,
      failures: category.tests
        .filter(t => t.status === 'failed')
        .map(t => ({ test: t.title, error: t.error }))
    };
  });
  
  report.score = totalTests > 0 
    ? Math.round((passedTests / totalTests) * 100) 
    : 0;
  
  return report;
}

function getErrorRecommendation(testTitle, error) {
  const lower = testTitle.toLowerCase();
  
  if (lower.includes('offline') || lower.includes('network')) {
    return 'Implement retry logic with exponential backoff and show clear offline indicators';
  }
  if (lower.includes('timeout')) {
    return 'Add configurable timeout limits and show progress indicators for long operations';
  }
  if (lower.includes('token') || lower.includes('auth')) {
    return 'Implement automatic token refresh and graceful session expiry handling';
  }
  if (lower.includes('empty') || lower.includes('validation')) {
    return 'Add client-side validation with clear error messages before submission';
  }
  
  return 'Review error handling logic and ensure user-friendly error messages';
}

function getSecurityImpact(testTitle) {
  const lower = testTitle.toLowerCase();
  
  if (lower.includes('sql')) {
    return 'Database compromise, data theft, unauthorized access';
  }
  if (lower.includes('xss')) {
    return 'Session hijacking, credential theft, malicious script execution';
  }
  if (lower.includes('csrf')) {
    return 'Unauthorized actions on behalf of authenticated users';
  }
  
  return 'Potential security breach';
}

function getSecurityMitigation(testTitle) {
  const lower = testTitle.toLowerCase();
  
  if (lower.includes('sql')) {
    return 'Use parameterized queries, ORM with proper escaping, input validation';
  }
  if (lower.includes('xss')) {
    return 'Implement Content Security Policy, sanitize all user input, use DOMPurify';
  }
  if (lower.includes('csrf')) {
    return 'Enforce CSRF tokens on all state-changing operations, validate origin headers';
  }
  
  return 'Review and implement security best practices';
}

function generateMarkdownReport(analysis, robustnessScore, errorReport, securityReport, recoveryReport) {
  const lines = [];
  
  lines.push('# Chaos Testing Report');
  lines.push('');
  lines.push(`**Generated:** ${new Date().toISOString()}`);
  lines.push(`**Robustness Score:** ${robustnessScore}/100`);
  lines.push('');
  
  lines.push('## Executive Summary');
  lines.push('');
  lines.push(`- **Total Tests:** ${analysis.total}`);
  lines.push(`- **Passed:** ${analysis.passed} ✅`);
  lines.push(`- **Failed:** ${analysis.failed} ❌`);
  lines.push(`- **Success Rate:** ${Math.round((analysis.passed / analysis.total) * 100)}%`);
  lines.push(`- **Security Risk Level:** ${securityReport.risk_level}`);
  lines.push('');
  
  lines.push('## Robustness Score Breakdown');
  lines.push('');
  Object.keys(analysis.categories).forEach(key => {
    const cat = analysis.categories[key];
    const score = cat.total > 0 ? Math.round((cat.passed / cat.total) * 100) : 0;
    const emoji = score >= 90 ? '🟢' : score >= 70 ? '🟡' : '🔴';
    
    lines.push(`### ${cat.name} ${emoji}`);
    lines.push(`- **Score:** ${score}% (Weight: ${cat.weight * 100}%)`);
    lines.push(`- **Tests:** ${cat.passed}/${cat.total} passed`);
    lines.push('');
  });
  
  lines.push('## Error Handling Assessment');
  lines.push('');
  Object.keys(errorReport.summary).forEach(category => {
    const summary = errorReport.summary[category];
    lines.push(`### ${category}`);
    lines.push(`- **Score:** ${summary.score}`);
    lines.push(`- **Results:** ${summary.passed}/${summary.total} passed`);
    lines.push('');
  });
  
  if (errorReport.details.length > 0) {
    lines.push('### Failed Error Handling Tests');
    lines.push('');
    errorReport.details.forEach(detail => {
      lines.push(`#### ${detail.test}`);
      lines.push(`- **Category:** ${detail.category}`);
      lines.push(`- **Error:** ${detail.error || 'Unknown'}`);
      lines.push(`- **Recommendation:** ${detail.recommendation}`);
      lines.push('');
    });
  }
  
  lines.push('## Security Vulnerability Report');
  lines.push('');
  lines.push(`**Risk Level:** ${securityReport.risk_level}`);
  lines.push('');
  
  if (securityReport.vulnerabilities.length > 0) {
    lines.push('### ⚠️ Vulnerabilities Found');
    lines.push('');
    securityReport.vulnerabilities.forEach(vuln => {
      lines.push(`#### ${vuln.test} [${vuln.severity}]`);
      lines.push(`- **Impact:** ${vuln.impact}`);
      lines.push(`- **Mitigation:** ${vuln.mitigation}`);
      lines.push('');
    });
  } else {
    lines.push('### ✅ No Critical Vulnerabilities Detected');
    lines.push('');
  }
  
  if (securityReport.passed.length > 0) {
    lines.push('### Security Tests Passed');
    lines.push('');
    securityReport.passed.forEach(test => {
      lines.push(`- ✅ ${test}`);
    });
    lines.push('');
  }
  
  lines.push('## Recovery Mechanism Evaluation');
  lines.push('');
  lines.push(`**Overall Recovery Score:** ${recoveryReport.score}%`);
  lines.push('');
  
  Object.keys(recoveryReport.mechanisms).forEach(mechanism => {
    const mech = recoveryReport.mechanisms[mechanism];
    const emoji = mech.status === 'EXCELLENT' ? '🟢' :
                  mech.status === 'GOOD' ? '🟡' :
                  mech.status === 'FAIR' ? '🟠' : '🔴';
    
    lines.push(`### ${mechanism} ${emoji}`);
    lines.push(`- **Status:** ${mech.status}`);
    lines.push(`- **Tests:** ${mech.passed}/${mech.total} passed`);
    
    if (mech.failures.length > 0) {
      lines.push('- **Failures:**');
      mech.failures.forEach(f => {
        lines.push(`  - ${f.test}: ${f.error || 'Unknown error'}`);
      });
    }
    lines.push('');
  });
  
  lines.push('## Recommendations');
  lines.push('');
  
  if (robustnessScore >= 90) {
    lines.push('✅ **Excellent robustness!** System handles errors gracefully.');
  } else if (robustnessScore >= 70) {
    lines.push('🟡 **Good robustness** with room for improvement in specific areas.');
  } else if (robustnessScore >= 50) {
    lines.push('🟠 **Fair robustness** - several error scenarios need attention.');
  } else {
    lines.push('🔴 **Poor robustness** - critical error handling issues detected.');
  }
  
  lines.push('');
  lines.push('### Priority Actions');
  lines.push('');
  
  if (securityReport.vulnerabilities.length > 0) {
    lines.push('1. **CRITICAL:** Address security vulnerabilities immediately');
  }
  
  Object.keys(analysis.categories).forEach(key => {
    const cat = analysis.categories[key];
    const score = cat.total > 0 ? (cat.passed / cat.total) * 100 : 0;
    
    if (score < 70) {
      lines.push(`2. Improve ${cat.name.toLowerCase()} (${Math.round(score)}% pass rate)`);
    }
  });
  
  lines.push('');
  lines.push('---');
  lines.push('');
  lines.push('*Generated by Chaos Testing Suite*');
  
  return lines.join('\n');
}

async function main() {
  console.log('🔥 Chaos Testing Suite\n');
  console.log('Running comprehensive error scenario tests...\n');
  
  const result = await runChaosTests();
  
  if (!result.output) {
    console.error('❌ No test output received');
    process.exit(1);
  }
  
  const parsed = parseTestResults(result.output);
  
  if (!parsed) {
    console.error('❌ Could not parse test results');
    console.log('\nRaw output:', result.output.substring(0, 500));
    process.exit(1);
  }
  
  const analysis = analyzeResults(parsed);
  const robustnessScore = calculateRobustnessScore(analysis);
  const errorReport = generateErrorHandlingReport(analysis);
  const securityReport = generateSecurityReport(analysis);
  const recoveryReport = generateRecoveryReport(analysis);
  
  const markdownReport = generateMarkdownReport(
    analysis,
    robustnessScore,
    errorReport,
    securityReport,
    recoveryReport
  );
  
  const reportPath = `./CHAOS_TEST_REPORT_${TIMESTAMP}.md`;
  writeFileSync(reportPath, markdownReport);
  
  const jsonPath = `./chaos-results-${TIMESTAMP}.json`;
  writeFileSync(jsonPath, JSON.stringify({
    analysis,
    robustnessScore,
    errorReport,
    securityReport,
    recoveryReport
  }, null, 2));
  
  console.log('\n📊 Test Results Summary\n');
  console.log(`Total Tests: ${analysis.total}`);
  console.log(`Passed: ${analysis.passed} ✅`);
  console.log(`Failed: ${analysis.failed} ❌`);
  console.log(`\nRobustness Score: ${robustnessScore}/100`);
  console.log(`Security Risk: ${securityReport.risk_level}`);
  console.log(`Recovery Score: ${recoveryReport.score}%`);
  
  console.log(`\n📄 Reports generated:`);
  console.log(`  - ${reportPath}`);
  console.log(`  - ${jsonPath}`);
  
  process.exit(analysis.failed > 0 ? 1 : 0);
}

main().catch(error => {
  console.error('❌ Fatal error:', error);
  process.exit(1);
});
