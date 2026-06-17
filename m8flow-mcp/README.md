# M8Flow MCP Server

[![Status](https://img.shields.io/badge/status-production-green)](#)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.4.2-blue)](https://gofastmcp.com)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)

MCP (Model Context Protocol) server for m8flow workflow management system. Provides 14 tools for managing process models, instances, and tasks through Claude Desktop.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- m8flow backend running on `localhost:6840`
- Valid JWT bearer token
- Claude Desktop

### Installation

```bash
# Clone or navigate to the project
cd c:/AOT/m8flow-mcp

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp sample.env .env
# Edit .env and add your M8FLOW_BEARER_TOKEN

# Test the server
python test_token_setup.py
```

### Configure Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "m8flow": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["-u", "C:\\AOT\\m8flow-mcp\\src\\main.py"],
      "env": {
        "PYTHONPATH": "C:\\AOT\\m8flow-mcp",
        "M8FLOW_BEARER_TOKEN": "your-jwt-token-here",
        "M8FLOW_API_URL": "http://localhost:6840",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Restart Claude Desktop and ask: **"list tasks in m8flow"**

---

## 🛠️ Available Tools

### Process Models (5 tools)
- `list_process_models` - List all workflow templates
- `get_process_model` - Get model details
- `create_process_model` - Create new workflow
- `update_process_model` - Update workflow
- `delete_process_model` - Delete workflow

### Process Instances (5 tools)
- `start_process_instance` - Start a workflow
- `list_process_instances` - List running workflows
- `get_process_instance` - Get instance details
- `cancel_process_instance` - Cancel a workflow
- `suspend_process_instance` - Suspend a workflow

### Tasks (4 tools)
- `list_tasks` - List user tasks ✅
- `get_task` - Get task details
- `complete_task` - Complete a task
- `claim_task` - Claim a task

---

## 🏗️ Architecture

```
Claude Desktop
      │
      ├─── MCP Protocol (stdio)
      │
      ▼
m8flow MCP Server (Python/FastMCP)
      │
      ├─── Global Auth Setup (JWT + Tenant ID)
      │
      ├─── 14 MCP Tools
      │
      ▼
m8flow Backend API (localhost:6840)
      │
      └─── Workflow Engine
```

**Key Design Decision:**  
Authentication is set **globally at server startup** rather than per-request via middleware, due to FastMCP 3.4.2 middleware hook limitations.

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `M8FLOW_BEARER_TOKEN` | ✅ | JWT token for authentication |
| `M8FLOW_API_URL` | ✅ | m8flow backend URL (default: localhost:6840) |
| `SERVER_TYPE` | No | `stdio` (default) or `remote` |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING` |

### JWT Token

The token must contain `m8flow_tenant_id` claim. Get it from:
1. m8flow frontend (browser DevTools → Network → Copy token)
2. Direct Keycloak ROPC authentication

Token expires after ~24 hours. See [docs/FINAL_SOLUTION.md](docs/FINAL_SOLUTION.md) for refresh instructions.

---

## 🧪 Testing

```bash
# Test authentication and API connectivity
python test_token_setup.py

# Interactive tool demo
python demo_mcp_tools.py

# List tasks directly via CLI
python -c "
import asyncio
from src.mcp_tools.tasks import list_tasks
print(asyncio.run(list_tasks()))
"
```

---

## 📁 Project Structure

```
m8flow-mcp/
├── src/
│   ├── main.py                 # Server entry point with global auth
│   ├── config/                 # Configuration & settings
│   ├── middleware/             # Request middleware
│   ├── mcp_tools/              # 14 MCP tool implementations
│   │   ├── process_models.py
│   │   ├── process_instances.py
│   │   └── tasks.py
│   ├── api_client.py           # HTTP client for m8flow API
│   ├── auth/                   # Authentication services
│   └── utils/                  # Logging, context management
├── tests/                      # Test scripts
├── .env                        # Environment configuration
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## 🐛 Troubleshooting

### "No authentication token available"
1. Check token is in `.env` and Claude Desktop config
2. Verify token hasn't expired (decode at jwt.io)
3. Check startup logs for "Authentication configured" message

### "Server disconnected"
1. Check Python path in Claude Desktop config
2. Verify `PYTHONPATH` is set correctly
3. Check logs at `%APPDATA%\Claude\logs\mcp-server-m8flow.log`

### "API returns 405/404"
1. Verify m8flow backend is running: `curl localhost:6840`
2. Check endpoint path in tool implementation
3. Ensure tenant ID is being sent in headers

---

## 🔐 Security

- **JWT tokens are sensitive** - Never commit to git
- `.env` file is git-ignored by default
- Token expires after 24 hours - refresh regularly
- Multi-tenant isolation via `m8flow_tenant_id` claim

---

## 🚀 Deployment

### Local Development
```bash
python -m src.main
```

### Production (Claude Desktop)
Configured via `claude_desktop_config.json` (see Quick Start above)

### Docker
```bash
docker-compose up
```

---

## 📊 Status

**Current Version:** 1.0 (Production Ready)  
**Status:** ✅ Working  
**Last Updated:** 2026-06-17

**Active Process:**
- Instance #2: Approval With Conditional Escalation
- Task: 2a0cba2f-0575-481f-bdf8-6dca2e44b301
- Assigned to: akhilaus

---

## 🤝 Contributing

1. Make changes
2. Test with `python test_token_setup.py`
3. Update documentation if needed

---

## 📝 License

[Add your license here]

---

## 🔗 Links

- **m8flow Backend:** http://localhost:6840
- **FastMCP:** https://gofastmcp.com
- **MCP Protocol:** https://modelcontextprotocol.io
