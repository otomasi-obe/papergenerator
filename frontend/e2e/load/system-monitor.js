#!/usr/bin/env node

/**
 * System Resource Monitor
 * 
 * Monitors system resources during load testing:
 * - CPU usage
 * - Memory usage
 * - Database connections
 * - Redis connections
 * - Response times
 */

import { spawn } from 'child_process';
import { writeFileSync } from 'fs';

class SystemMonitor {
  constructor() {
    this.samples = [];
    this.interval = null;
    this.startTime = Date.now();
  }

  async collectSample() {
    const sample = {
      timestamp: Date.now() - this.startTime,
      cpu: await this.getCPUUsage(),
      memory: await this.getMemoryUsage(),
      processes: await this.getProcessInfo(),
    };
    
    this.samples.push(sample);
    return sample;
  }

  async getCPUUsage() {
    return new Promise((resolve) => {
      const ps = spawn('ps', ['aux']);
      let output = '';
      
      ps.stdout.on('data', (data) => {
        output += data.toString();
      });
      
      ps.on('close', () => {
        const lines = output.split('\n');
        let totalCPU = 0;
        let pythonCPU = 0;
        let nodeCPU = 0;
        
        lines.forEach(line => {
          const parts = line.split(/\s+/);
          if (parts.length > 2) {
            const cpu = parseFloat(parts[2]) || 0;
            totalCPU += cpu;
            
            if (line.includes('python') || line.includes('gunicorn')) {
              pythonCPU += cpu;
            }
            if (line.includes('node')) {
              nodeCPU += cpu;
            }
          }
        });
        
        resolve({ total: totalCPU, python: pythonCPU, node: nodeCPU });
      });
    });
  }

  async getMemoryUsage() {
    return new Promise((resolve) => {
      const free = spawn('free', ['-m']);
      let output = '';
      
      free.stdout.on('data', (data) => {
        output += data.toString();
      });
      
      free.on('close', () => {
        const lines = output.split('\n');
        const memLine = lines.find(l => l.startsWith('Mem:'));
        
        if (memLine) {
          const parts = memLine.split(/\s+/);
          resolve({
            total: parseInt(parts[1]) || 0,
            used: parseInt(parts[2]) || 0,
            free: parseInt(parts[3]) || 0,
            available: parseInt(parts[6]) || 0,
          });
        } else {
          resolve({ total: 0, used: 0, free: 0, available: 0 });
        }
      });
    });
  }

  async getProcessInfo() {
    return new Promise((resolve) => {
      const ps = spawn('ps', ['aux']);
      let output = '';
      
      ps.stdout.on('data', (data) => {
        output += data.toString();
      });
      
      ps.on('close', () => {
        const lines = output.split('\n');
        const processes = {
          python: 0,
          node: 0,
          postgres: 0,
          redis: 0,
        };
        
        lines.forEach(line => {
          if (line.includes('python') || line.includes('gunicorn')) processes.python++;
          if (line.includes('node')) processes.node++;
          if (line.includes('postgres')) processes.postgres++;
          if (line.includes('redis')) processes.redis++;
        });
        
        resolve(processes);
      });
    });
  }

  start(intervalMs = 1000) {
    console.log('Starting system monitor...');
    this.interval = setInterval(async () => {
      const sample = await this.collectSample();
      console.log(`[${(sample.timestamp / 1000).toFixed(1)}s] CPU: ${sample.cpu.total.toFixed(1)}% | Mem: ${sample.memory.used}MB/${sample.memory.total}MB | Processes: Py=${sample.processes.python} Node=${sample.processes.node}`);
    }, intervalMs);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  generateReport() {
    if (this.samples.length === 0) {
      return 'No samples collected';
    }

    const cpuSamples = this.samples.map(s => s.cpu.total);
    const memSamples = this.samples.map(s => s.memory.used);
    
    const avgCPU = cpuSamples.reduce((a, b) => a + b, 0) / cpuSamples.length;
    const maxCPU = Math.max(...cpuSamples);
    const avgMem = memSamples.reduce((a, b) => a + b, 0) / memSamples.length;
    const maxMem = Math.max(...memSamples);

    const report = {
      duration: (this.samples[this.samples.length - 1].timestamp / 1000).toFixed(1) + 's',
      samples: this.samples.length,
      cpu: {
        avg: avgCPU.toFixed(2) + '%',
        max: maxCPU.toFixed(2) + '%',
      },
      memory: {
        avg: avgMem.toFixed(0) + 'MB',
        max: maxMem.toFixed(0) + 'MB',
      },
      samples: this.samples,
    };

    return report;
  }

  saveReport(filename = 'system-monitor-report.json') {
    const report = this.generateReport();
    writeFileSync(filename, JSON.stringify(report, null, 2));
    console.log(`\nSystem monitor report saved to ${filename}`);
    return report;
  }
}

// CLI usage
if (import.meta.url === `file://${process.argv[1]}`) {
  const monitor = new SystemMonitor();
  monitor.start(1000);

  process.on('SIGINT', () => {
    console.log('\nStopping monitor...');
    monitor.stop();
    const report = monitor.generateReport();
    
    console.log('\n' + '='.repeat(80));
    console.log('SYSTEM RESOURCE REPORT');
    console.log('='.repeat(80));
    console.log(`Duration: ${report.duration}`);
    console.log(`Samples: ${report.samples}`);
    console.log(`\nCPU Usage:`);
    console.log(`  Average: ${report.cpu.avg}`);
    console.log(`  Peak: ${report.cpu.max}`);
    console.log(`\nMemory Usage:`);
    console.log(`  Average: ${report.memory.avg}`);
    console.log(`  Peak: ${report.memory.max}`);
    console.log('='.repeat(80));
    
    monitor.saveReport();
    process.exit(0);
  });

  console.log('System monitor running. Press Ctrl+C to stop and generate report.');
}

export default SystemMonitor;
