#!/usr/bin/env node

/**
 * Load Test Results Analyzer
 * 
 * Analyzes Playwright test results and generates comprehensive reports:
 * - Performance metrics
 * - Bottleneck identification
 * - Scalability assessment
 * - Recommendations
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

class LoadTestAnalyzer {
  constructor(resultsFile = 'load-test-results.json') {
    this.resultsFile = resultsFile;
    this.results = null;
  }

  loadResults() {
    if (!existsSync(this.resultsFile)) {
      throw new Error(`Results file not found: ${this.resultsFile}`);
    }

    const data = readFileSync(this.resultsFile, 'utf-8');
    this.results = JSON.parse(data);
    return this.results;
  }

  analyzePerformance() {
    if (!this.results) {
      this.loadResults();
    }

    const suites = this.results.suites || [];
    const allTests = [];
    
    const extractTests = (suite) => {
      if (suite.specs) {
        suite.specs.forEach(spec => {
          spec.tests.forEach(test => {
            allTests.push({
              title: spec.title,
              status: test.status,
              duration: test.results[0]?.duration || 0,
              error: test.results[0]?.error,
            });
          });
        });
      }
      if (suite.suites) {
        suite.suites.forEach(extractTests);
      }
    };

    suites.forEach(extractTests);

    const passed = allTests.filter(t => t.status === 'passed').length;
    const failed = allTests.filter(t => t.status === 'failed').length;
    const durations = allTests.map(t => t.duration);
    
    const sorted = [...durations].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);

    return {
      totalTests: allTests.length,
      passed,
      failed,
      successRate: ((passed / allTests.length) * 100).toFixed(2) + '%',
      duration: {
        total: (sum / 1000).toFixed(2) + 's',
        avg: (sum / allTests.length).toFixed(2) + 'ms',
        min: sorted[0].toFixed(2) + 'ms',
        max: sorted[sorted.length - 1].toFixed(2) + 'ms',
        p50: sorted[Math.floor(sorted.length * 0.5)].toFixed(2) + 'ms',
        p95: sorted[Math.floor(sorted.length * 0.95)].toFixed(2) + 'ms',
        p99: sorted[Math.floor(sorted.length * 0.99)].toFixed(2) + 'ms',
      },
      failures: allTests.filter(t => t.status === 'failed'),
    };
  }

  identifyBottlenecks() {
    const perf = this.analyzePerformance();
    const bottlenecks = [];

    // High failure rate
    const failureRate = (perf.failed / perf.totalTests) * 100;
    if (failureRate > 10) {
      bottlenecks.push({
        type: 'HIGH_FAILURE_RATE',
        severity: 'critical',
        description: `${failureRate.toFixed(1)}% of tests failed`,
        recommendation: 'Investigate error logs and database connection pool settings',
      });
    }

    // Slow response times
    const p95 = parseFloat(perf.duration.p95);
    if (p95 > 5000) {
      bottlenecks.push({
        type: 'SLOW_RESPONSE_TIME',
        severity: 'high',
        description: `P95 response time is ${perf.duration.p95}`,
        recommendation: 'Check database query performance and add indexes',
      });
    } else if (p95 > 2000) {
      bottlenecks.push({
        type: 'MODERATE_RESPONSE_TIME',
        severity: 'medium',
        description: `P95 response time is ${perf.duration.p95}`,
        recommendation: 'Consider caching frequently accessed data',
      });
    }

    // High variance in response times
    const max = parseFloat(perf.duration.max);
    const avg = parseFloat(perf.duration.avg);
    if (max > avg * 5) {
      bottlenecks.push({
        type: 'HIGH_VARIANCE',
        severity: 'medium',
        description: `Max response time (${perf.duration.max}) is ${(max/avg).toFixed(1)}x the average`,
        recommendation: 'Some operations are significantly slower - investigate outliers',
      });
    }

    return bottlenecks;
  }

  assessScalability() {
    const perf = this.analyzePerformance();
    const bottlenecks = this.identifyBottlenecks();

    let score = 100;
    let grade = 'A';

    // Deduct points for failures
    const failureRate = (perf.failed / perf.totalTests) * 100;
    score -= failureRate * 2;

    // Deduct points for slow responses
    const p95 = parseFloat(perf.duration.p95);
    if (p95 > 5000) score -= 30;
    else if (p95 > 2000) score -= 15;
    else if (p95 > 1000) score -= 5;

    // Deduct points for bottlenecks
    bottlenecks.forEach(b => {
      if (b.severity === 'critical') score -= 20;
      else if (b.severity === 'high') score -= 10;
      else if (b.severity === 'medium') score -= 5;
    });

    score = Math.max(0, Math.min(100, score));

    if (score >= 90) grade = 'A';
    else if (score >= 80) grade = 'B';
    else if (score >= 70) grade = 'C';
    else if (score >= 60) grade = 'D';
    else grade = 'F';

    let assessment = '';
    if (score >= 90) {
      assessment = 'Excellent - System handles concurrent load well';
    } else if (score >= 80) {
      assessment = 'Good - System is stable with minor performance issues';
    } else if (score >= 70) {
      assessment = 'Fair - System works but has noticeable performance degradation';
    } else if (score >= 60) {
      assessment = 'Poor - System struggles under concurrent load';
    } else {
      assessment = 'Critical - System cannot handle concurrent load reliably';
    }

    return {
      score: score.toFixed(1),
      grade,
      assessment,
      recommendations: this.generateRecommendations(bottlenecks, perf),
    };
  }

  generateRecommendations(bottlenecks, perf) {
    const recommendations = [];

    // Based on bottlenecks
    bottlenecks.forEach(b => {
      recommendations.push(b.recommendation);
    });

    // General recommendations
    const failureRate = (perf.failed / perf.totalTests) * 100;
    if (failureRate > 0) {
      recommendations.push('Review application logs for error patterns');
      recommendations.push('Implement retry logic for transient failures');
    }

    const p95 = parseFloat(perf.duration.p95);
    if (p95 > 1000) {
      recommendations.push('Consider implementing request queuing and rate limiting');
      recommendations.push('Add monitoring and alerting for slow requests');
    }

    if (recommendations.length === 0) {
      recommendations.push('System is performing well - continue monitoring');
      recommendations.push('Consider testing with higher concurrency levels');
    }

    return [...new Set(recommendations)]; // Remove duplicates
  }

  generateReport() {
    const perf = this.analyzePerformance();
    const bottlenecks = this.identifyBottlenecks();
    const scalability = this.assessScalability();

    return {
      summary: {
        totalTests: perf.totalTests,
        passed: perf.passed,
        failed: perf.failed,
        successRate: perf.successRate,
      },
      performance: perf.duration,
      bottlenecks,
      scalability,
      failures: perf.failures,
    };
  }

  printReport() {
    const report = this.generateReport();

    console.log('\n' + '='.repeat(80));
    console.log('LOAD TEST ANALYSIS REPORT');
    console.log('='.repeat(80));

    console.log('\n📊 SUMMARY');
    console.log('-'.repeat(80));
    console.log(`Total Tests: ${report.summary.totalTests}`);
    console.log(`Passed: ${report.summary.passed}`);
    console.log(`Failed: ${report.summary.failed}`);
    console.log(`Success Rate: ${report.summary.successRate}`);

    console.log('\n⚡ PERFORMANCE METRICS');
    console.log('-'.repeat(80));
    console.log(`Total Duration: ${report.performance.total}`);
    console.log(`Average: ${report.performance.avg}`);
    console.log(`Min: ${report.performance.min}`);
    console.log(`Max: ${report.performance.max}`);
    console.log(`P50: ${report.performance.p50}`);
    console.log(`P95: ${report.performance.p95}`);
    console.log(`P99: ${report.performance.p99}`);

    if (report.bottlenecks.length > 0) {
      console.log('\n🚨 BOTTLENECKS IDENTIFIED');
      console.log('-'.repeat(80));
      report.bottlenecks.forEach((b, i) => {
        const icon = b.severity === 'critical' ? '🔴' : b.severity === 'high' ? '🟠' : '🟡';
        console.log(`\n${i + 1}. ${icon} ${b.type} (${b.severity})`);
        console.log(`   ${b.description}`);
        console.log(`   → ${b.recommendation}`);
      });
    }

    console.log('\n📈 SCALABILITY ASSESSMENT');
    console.log('-'.repeat(80));
    console.log(`Score: ${report.scalability.score}/100 (Grade: ${report.scalability.grade})`);
    console.log(`Assessment: ${report.scalability.assessment}`);

    console.log('\n💡 RECOMMENDATIONS');
    console.log('-'.repeat(80));
    report.scalability.recommendations.forEach((rec, i) => {
      console.log(`${i + 1}. ${rec}`);
    });

    if (report.failures.length > 0) {
      console.log('\n❌ FAILED TESTS');
      console.log('-'.repeat(80));
      report.failures.slice(0, 10).forEach((f, i) => {
        console.log(`\n${i + 1}. ${f.title}`);
        if (f.error) {
          console.log(`   Error: ${f.error.message || f.error}`);
        }
      });
      if (report.failures.length > 10) {
        console.log(`\n... and ${report.failures.length - 10} more failures`);
      }
    }

    console.log('\n' + '='.repeat(80));
  }
}

// CLI usage
if (import.meta.url === `file://${process.argv[1]}`) {
  const analyzer = new LoadTestAnalyzer();
  
  try {
    analyzer.printReport();
  } catch (error) {
    console.error('Error analyzing results:', error.message);
    console.error('Make sure to run the load tests first to generate results.');
    process.exit(1);
  }
}

export default LoadTestAnalyzer;
