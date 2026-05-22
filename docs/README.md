# PaperFull Documentation

Welcome to the PaperFull documentation. This guide will help you understand, develop, deploy, and operate the PaperFull academic paper generation platform.

## 🚀 Quick Links

- **New Developer?** Start with [Quick Start Guide](development/quick-start.md)
- **Need API docs?** See [API Documentation](api/README.md)
- **Deploying?** Check [Production Setup](deployment/production-setup.md)
- **Troubleshooting?** Visit [Common Issues](troubleshooting/common-issues.md)

## 📚 Documentation Sections

### [Architecture](architecture/README.md)
System design, component interactions, data flow, and technical decisions.

- [System Overview](architecture/system-overview.md) - High-level architecture
- [Component Diagram](architecture/component-diagram.md) - Component interactions
- [Data Flow](architecture/data-flow.md) - Key workflows
- [Database Schema](architecture/database-schema.md) - Database structure
- [Deployment Architecture](architecture/deployment-architecture.md) - Production setup
- [Tech Stack](architecture/tech-stack.md) - Technology choices
- [Decision Records](architecture/decision-records/) - Architecture decisions (ADRs)

### [API Documentation](api/README.md)
REST API reference, authentication, and integration guides.

- [OpenAPI Specification](api/openapi.yaml) - Complete API spec
- [Authentication](api/authentication.md) - OAuth & JWT flow
- [Chat API](api/chat-api.md) - Chat endpoints
- [Paper API](api/paper-api.md) - Paper generation endpoints
- [SLR API](api/slr-api.md) - Systematic Literature Review endpoints
- [Files API](api/files-api.md) - File upload endpoints
- [Charts API](api/charts-api.md) - Chart generation endpoints

### [Development](development/README.md)
Setup, coding standards, testing, and contribution guidelines.

- [Quick Start](development/quick-start.md) - Get started in 5 minutes ⚡
- [Setup Guide](development/setup.md) - Detailed setup instructions
- [Project Structure](development/project-structure.md) - Codebase organization
- [Coding Standards](development/coding-standards.md) - Code style & conventions
- [Testing Guide](development/testing.md) - Testing strategy
- [Debugging Guide](development/debugging.md) - Debugging tips
- [Contributing](development/contributing.md) - How to contribute
- [Git Workflow](development/git-workflow.md) - Branching & PR process

### [Deployment](deployment/README.md)
Production deployment, monitoring, and operations.

- [Production Setup](deployment/production-setup.md) - Server setup
- [Environment Variables](deployment/environment-variables.md) - Configuration
- [Database Migrations](deployment/database-migrations.md) - Alembic guide
- [Monitoring](deployment/monitoring.md) - Prometheus/Grafana
- [Backup & Restore](deployment/backup-restore.md) - Backup procedures
- [Security](deployment/security.md) - Security best practices
- [CI/CD](deployment/ci-cd.md) - Continuous integration

### [Features](features/README.md)
Feature documentation and user workflows.

- [Paper Generation](features/paper-generation.md) - Core feature
- [SLR Workflow](features/slr-workflow.md) - Literature review
- [Chat Interface](features/chat-interface.md) - AI chat
- [Multi-Question](features/multi-question.md) - Question workflow
- [File Uploads](features/file-uploads.md) - File handling
- [Image Generation](features/image-generation.md) - Image creation
- [Chart Generation](features/chart-generation.md) - Chart creation
- [Citation Management](features/citation-management.md) - Citations

### [Troubleshooting](troubleshooting/README.md)
Common issues, error codes, and solutions.

- [Common Issues](troubleshooting/common-issues.md) - FAQ
- [Error Codes](troubleshooting/error-codes.md) - Error reference
- [Performance Issues](troubleshooting/performance.md) - Performance
- [Database Issues](troubleshooting/database-issues.md) - DB problems
- [Worker Issues](troubleshooting/worker-issues.md) - Queue problems

### [Operations](operations/README.md)
Operational runbooks and procedures.

- [Monitoring & Alerts](operations/monitoring-alerts.md) - Alert responses
- [Log Analysis](operations/log-analysis.md) - Log locations
- [Health Checks](operations/health-checks.md) - Health endpoints
- [Runbooks](operations/runbooks/) - Operational procedures

### [Reference](reference/README.md)
Technical reference and glossary.

- [Model Configuration](reference/model-configuration.md) - AI models
- [Prompt Engineering](reference/prompt-engineering.md) - Prompts
- [Tool Registry](reference/tool-registry.md) - Chat tools
- [Glossary](reference/glossary.md) - Terms & definitions

## 🎯 Common Tasks

### I want to...

**...set up the project locally**
→ [Quick Start Guide](development/quick-start.md)

**...understand the architecture**
→ [System Overview](architecture/system-overview.md)

**...run tests**
→ [Testing Guide](development/testing.md)

**...deploy to production**
→ [Production Setup](deployment/production-setup.md)

**...integrate with the API**
→ [API Documentation](api/README.md)

**...fix a bug**
→ [Debugging Guide](development/debugging.md) + [Troubleshooting](troubleshooting/common-issues.md)

**...add a new feature**
→ [Contributing Guide](development/contributing.md)

**...understand a feature**
→ [Features Documentation](features/README.md)

## 📖 Documentation Standards

All documentation follows these standards:
- Written in Markdown
- Diagrams use Mermaid syntax
- Code examples are tested
- Links are relative
- Updated with code changes

## 🤝 Contributing to Documentation

Documentation is as important as code. When contributing:

1. Update docs in the same PR as code changes
2. Follow the [documentation templates](../DOCUMENTATION_PLAN.md#4-documentation-templates)
3. Use Mermaid for diagrams
4. Include code examples
5. Link related documents

See [Contributing Guide](development/contributing.md) for details.

## 📝 Documentation Status

| Section | Status | Last Updated |
|---------|--------|--------------|
| Architecture | 🟡 In Progress | 2026-05-22 |
| API | 🟢 Complete | 2026-05-22 |
| Development | 🟡 In Progress | 2026-05-22 |
| Deployment | 🔴 Planned | - |
| Features | 🔴 Planned | - |
| Troubleshooting | 🔴 Planned | - |
| Operations | 🔴 Planned | - |
| Reference | 🔴 Planned | - |

Legend: 🟢 Complete | 🟡 In Progress | 🔴 Planned

## 🔗 External Resources

- **Production**: https://paperfull.app
- **Repository**: (Add GitHub/GitLab URL)
- **Issue Tracker**: (Add issue tracker URL)
- **Team Chat**: (Add Slack/Discord URL)

## 📞 Support

- **Technical Issues**: See [Troubleshooting](troubleshooting/common-issues.md)
- **Feature Requests**: Open an issue
- **Security Issues**: Contact security team directly

---

**Last Updated**: 2026-05-22  
**Documentation Version**: 1.0.0  
**Application Version**: 1.0.0
