# 🚀 M8Flow MCP Server

**Model Context Protocol (MCP) server for M8Flow workflow automation platform**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-27%2F27%20passing-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-70.59%25%20(visualization)-green.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 🎯 **Overview**

M8Flow MCP enables Claude Desktop to interact with M8Flow's BPMN workflow automation platform through the Model Context Protocol. This integration allows natural language workflow management, execution, and BPMN content retrieval.

---

## ✨ **Key Features**

### **29 Tools Available:**
- **Process Groups** (5 tools) - Organize workflows
- **Process Models** (5 tools) - Manage BPMN definitions
- **Process Instances** (5 tools) - Execute & monitor workflows
- **Tasks** (4 tools) - Handle user tasks
- **Templates** (3 tools) - Pre-built workflows
- **Visualization** (3 tools) - Retrieve BPMN XML content
- **Connectors** (4 tools) - Explore and use 43 connector operations

### **BPMN Content Retrieval:**
- Get BPMN XML for workflows, templates, and instances
- Save to files for viewing in external BPMN tools
- Works in local & ECS deployment modes

### **Deployment Modes:**
- **Local Mode:** Development & testing
- **ECS Mode:** Production multi-user deployment

---

## 📦 **Installation**

### **Prerequisites:**
- Python 3.8+
- M8Flow API access (URL + Bearer Token)
- Claude Desktop (for usage)

### **Setup:**

```bash
# Clone repository
git clone <repository-url>
cd m8flow-mcp

# Install dependencies
pip install -e .

# Configure environment
export M8FLOW_API_URL="https://your-m8flow-instance.com/api"
export M8FLOW_BEARER_TOKEN="your-bearer-token"
export DEPLOYMENT_MODE="local"  # or "ecs" for production
```

---

## 🚀 **Quick Start**

### **1. Configure Claude Desktop**

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "m8flow": {
      "command": "python",
      "args": ["-m", "src.server"],
      "env": {
        "M8FLOW_API_URL": "https://your-instance.com/api",
        "M8FLOW_BEARER_TOKEN": "your-token",
        "DEPLOYMENT_MODE": "local"
      }
    }
  }
}
```

### **2. Use with Claude Desktop**

Open Claude Desktop and ask:

```
"Show me all workflows in M8Flow"
"Get the BPMN content for single-approval"
"Start an instance of my-workflow"
```

---

## 📚 **Documentation**

### **Main Documentation:**
- **[Claude Instructions](docs/CLAUDE_INSTRUCTIONS.md)** - For Claude AI
- **[ECS Deployment](docs/ECS_TASK_DEFINITION_UPDATE.md)** - AWS ECS setup
- **[Complete Documentation](docs/M8Flow-MCP-Complete-Documentation.md)** - Full reference

### **Excel Documentation:**
- **M8Flow-MCP-Complete-Documentation.xlsx** - 12 sheets with complete details
  - All 25 tools
  - All 27 test cases
  - Architecture diagrams
  - Deployment guides

### **Additional Docs:**
- [Architecture](docs/ARCHITECTURE_EXPLAINED.md)
- [API Reference](docs/API_REFERENCE.md)
- [Test Status](docs/CI_TEST_STATUS.md)
- [Features](docs/FEATURES_DETAILED_EXPLANATION.md)

---

## 🧪 **Testing**

### **Run All Tests:**

```bash
# Run unit tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run deployment smoke tests
python test_deployment.py --verbose
```

### **Test Status:**
- ✅ 27/27 tests passing (100%)
- ✅ 70.59% visualization coverage
- ✅ All deployment modes tested
- ✅ Edge cases covered

---

## 🏗️ **Architecture**

### **Components:**

```
┌─────────────────┐
│ Claude Desktop  │  User requests workflow data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  M8Flow MCP     │  Fetches data from M8Flow API
│  Server         │  Returns BPMN XML & workflow info
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Claude AI      │  Displays results to user
└─────────────────┘
```

---

## 📂 **Project Structure**

```
m8flow-mcp/
├── src/
│   ├── server.py              # MCP server entry point
│   ├── api_client.py          # M8Flow API client
│   └── mcp_tools/             # MCP tool implementations
│       ├── process_groups.py
│       ├── process_models.py
│       ├── process_instances.py
│       ├── tasks.py
│       ├── templates.py
│       └── visualization.py   # BPMN visualization
│
├── tools/                     # Utility tools
│
├── tests/
│   ├── unit/                  # Unit tests (27 tests)
│   └── manual/                # Manual integration tests
│
├── docs/                      # All documentation
│
├── pyproject.toml             # Project dependencies
├── README.md                  # This file
└── M8Flow-MCP-Complete-Documentation.xlsx  # Excel docs
```

---

## 📄 **BPMN Content Examples**

### **Get Workflow BPMN:**
```
User: "Get the BPMN content for the approval workflow"

Claude calls: view_workflow("approval-group/approval-workflow")

Result: Returns BPMN XML content and saves to temp file
```

### **Get Template BPMN:**
```
User: "Get the BPMN for template 1"

Claude calls: view_workflow_from_template(1)

Result: Returns template BPMN XML content
```

### **Get Instance BPMN:**
```
User: "Get the workflow BPMN for instance 123"

Claude calls: view_process_instance("model-id", 123)

Result: Returns instance BPMN XML with status
```

---

## 🛠️ **Development**

### **Local Development:**

```bash
# Install in editable mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check src/ tests/

# Type checking
mypy src/
```

### **Adding New Tools:**

1. Create tool in `src/mcp_tools/`
2. Add tests in `tests/unit/`
3. Update documentation
4. Run `pytest` to verify

---

## 🚢 **Deployment**

### **Local Mode (Development):**

```bash
# Set environment
export DEPLOYMENT_MODE=local

# Start server
python -m src.server

# Start auto-viewer (separate terminal)
python tools/auto-viewer/auto_viewer.py
```

### **ECS Mode (Production):**

1. **Update ECS Task Definition:**
   - Add `DEPLOYMENT_MODE=ecs` environment variable
   - Deploy updated task definition

**See:** [ECS Deployment Guide](docs/ECS_TASK_DEFINITION_UPDATE.md)

---

## 📊 **Statistics**

| Metric | Value |
|--------|-------|
| **Total Tools** | 25 |
| **Test Cases** | 27 |
| **Test Pass Rate** | 100% |
| **Content Retrieval Coverage** | 70.59% |
| **Overall Coverage** | 9.94% |
| **Deployment Modes** | 2 (Local & ECS) |
| **Documentation Files** | 20+ |

---

## 🏆 **Unique Features**

### **vs Other MCPs:**

| Feature | M8Flow MCP | n8n-MCP | mcp-camunda |
|---------|------------|---------|-------------|
| BPMN Content Retrieval | ✅ Yes | ❌ No | ❌ No |
| Template Management | ✅ Yes | ❌ No | ❌ No |
| Pure Python | ✅ Yes | ❌ No | ❌ No |
| Multi-User ECS | ✅ Yes | ❌ No | ❌ No |

---

## 🤝 **Contributing**

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

---

## 📝 **License**

MIT License - See LICENSE file for details

---

## 📞 **Support**

- **Documentation:** [docs/](docs/)
- **Issues:** GitHub Issues
- **API Docs:** [M8Flow API Documentation](https://m8flow.ai/docs)

---

## 🎯 **Quick Links**

- [User Guide](docs/USER_GUIDE_VISUALIZATION.md) - Get started with visualization
- [Test Status](docs/CI_TEST_STATUS.md) - Current test results
- [Architecture](docs/ARCHITECTURE_EXPLAINED.md) - Technical architecture
- [Deployment](docs/ECS_TASK_DEFINITION_UPDATE.md) - Production deployment

---

**Built with ❤️ for the M8Flow community**

🚀 **Ready for production use!** ✅
