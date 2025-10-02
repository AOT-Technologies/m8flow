# m8flow v0.8 — Python-based workflow engine
<div align="center">
    <img src="./docs/m8flow_logo.png" alt-text="m8flow"/>
</div>

**m8flow** is an open-source workflow engine implemented in pure Python.  
It is built on the proven foundation of SpiffWorkflow, with a vision shaped by **8 guiding principles** for flow orchestration:

**Merge flows effectively** – streamline complex workflows  
**Make apps faster** – speed up development and deployment  
**Manage processes better** – bring structure and clarity to execution  
**Minimize errors** – reduce mistakes through automation  
**Maximize efficiency** – get more done with fewer resources  
**Model workflows visually** – design with simplicity and clarity  
**Modernize systems** – upgrade legacy processes seamlessly  
**Mobilize innovation** – empower teams to build and experiment quickly  

---

## Why m8flow?

**Future-proof alternative** → replaces Camunda 7 with a modern, Python-based workflow engine  
**Enterprise-grade integrations** → tight alignment with **formsflow.ai**, **caseflow**, and the **SLED360** automation suite  
**Open and extensible** → open source by default, extensible for enterprise-grade use cases  
**Principles-first branding** → “m8” = 8 principles for flow, consistent with the product family (caseflow, formsflow.ai)  
**Visual and symbolic meaning**:  
  - “8 nodes” in automation  
  - “8” resembles a curled Python → Python-native identity  
  - “m8” → mate / mighty → collaboration and strength  

---

## Features

**BPMN 2.0**: pools, lanes, multi-instance tasks, sub-processes, timers, signals, messages, boundary events, loops  
**DMN**: baseline implementation integrated with the Python execution engine  
**Forms support**: extract form definitions (Camunda XML extensions → JSON) for CLI or web UI generation  
**Python-native workflows**: run workflows via Python code or JSON structures  
**Integration-ready**: designed to plug into formsflow, caseflow, decision engines, and enterprise observability tools  

_A complete list of the latest features is available in our [release notes](https://github.com/AOT-Technologies/m8flow/releases)._  

---

## Roadmap

**v1.0 (Jan 2026)** → Foundation release (standalone + formsflow integration)  
**Summer 2026** → Feature updates (templates, connectors, monitoring) + security iFixes  
**2027 onward** → Yearly feature releases, quarterly iFixes, enterprise add-ons (dashboards, connectors, observability)  

---

## Installation

### Backend Setup, local

Remember, if you don't need a full-on native dev experience, you can run with docker (see below), which saves you from all the native setup.
If you have issues with the local dev setup, please consult [the troubleshooting guide](https://spiff-arena.readthedocs.io/en/latest/Support/Running_Server_Locally.html).

There are three prerequisites for non-docker local development:

1. python - [asdf-vm](https://asdf-vm.com) works well for installing this.
2. uv - 'pip install uv` works, but recommend standalone installer, see <https://github.com/astral-sh/uv>
3. mysql - the app also supports postgres. and sqlite, if you are talking local dev).

When these are installed, you are ready for:

```bash
    cd spiffworkflow-backend
    uv sync
    ./bin/recreate_db clean
    ./bin/run_server_locally
    ./bin/run_server_locally keycloak # if you want to use keycloak instead of the built-in openid server
```

**Mac Port Errors**: On a Mac, port 7000 (used by the backend) might be hijacked by Airplay. For those who upgraded to macOS 12.1 and are running everything locally, your AirPlay receiver may have started on Port 7000 and your server (which uses port 7000 by default) may fail due to this port already being used. You can disable this port in System Preferences > Sharing > AirPlay receiver.

**Poetry Install Errors**: If you encounter errors with the Poetry install, please note that MySQL and PostgreSQL may require certain packages exist on your system prior to installing these libraries.
Please see the [PyPi mysqlclient instructions](https://pypi.org/project/mysqlclient/) and the pre-requisites for the [Postgres psycopq2 adapter](https://www.psycopg.org/docs/install.html#prerequisites) Following the instructions here carefully will assure your OS has the right dependencies installed.
Correct these, and rerun the above commands.

**Using PyCharm?** If you would like to run or debug your project within an editor like PyCharm please see
[These directions for PyCharm Setup](spiffworkflow-backend/docs/pycharm.md).

### Keycloak Setup

You will want an openid server of some sort for authentication.
There is one built in to the app that is used in the docker compose setup for simplicity, but this is not to be used in production
If you are using `./bin/run_server_locally keycloak`, you can fire up a companion keycloak for local dev like this:

    ./keycloak/bin/start_keycloak

It'll be running on port 7002.
If you want to log in to the keycloak admin console, it can be found at <http://localhost:7002>, and the creds are admin/admin (also logs you in to the app if running the frontend)

### Frontend Setup, local

First install nodejs (also installable via asdf-vm), ideally the version in .tool-versions (but likely other versions will work). Then:

    cd spiffworkflow-frontend
    npm install
    npm start

Assuming you're running Keycloak as indicated above, you can log in with admin/admin.

### Run tests

    ./bin/run_pyl

### Run cypress automated browser tests

Get the app running so you can access the frontend at <http://localhost:7001> in your browser by following the frontend and backend setup steps above, and then:

    ./bin/run_cypress_tests_locally

### Docker

For full instructions, see [Running SpiffWorkflow Locally with Docker](https://www.spiffworkflow.org/posts/articles/get_started_docker/).

The `docker-compose.yml` file is for running a full-fledged instance of spiff-arena while `editor.docker-compose.yml` provides BPMN graphical editor capability to libraries and projects that depend on SpiffWorkflow but have no built-in BPMN edit capabilities.

#### Using Docker for Local Development

If you have `docker` and `docker compose`, as an alternative to locally installing the required dependencies, you can leverage the development docker containers and `Makefile` while working locally. To use, clone the repo and run `make`. This will build the required images, install all dependencies, start the servers and run the linting and tests. Once complete you can [open the app](http://localhost:8001) and code changes will be reflected while running.

After the containers are set up, you can run `make start-dev` and `make stop-dev` to start and stop the servers. If the frontend or backend lock file changes, `make dev-env` will recreate the containers with the new dependencies.

Please refer to the [Makefile](Makefile) as the source of truth, but for a summary of the available `make` targets:

| Target       | Action                                                                                      |
| ------------ | ------------------------------------------------------------------------------------------- |
| dev-env      | Builds the images, sets up the backend db and installs `npm` and `uv` dependencies          |
| start-dev    | Starts the frontend and backend servers, also stops them first if they were already running |
| stop-dev     | Stops the frontend and backend servers                                                      |
| be-tests-par | Runs the backend unit tests in parallel                                                     |
| fe-lint-fix  | Runs `npm lint:fix` in the frontend container                                               |
| run-pyl      | Runs all frontend and backend lints, backend unit tests                                     |

--- 

## Contribute

We welcome contributions from the community!

  - Submit PRs with passing tests and clear references to issues  

  ---

## Credits

m8flow builds upon the outstanding work of the **SpiffWorkflow community** and contributors over the past decade. We extend gratitude to:

  - Samuel Abels (@knipknap), Matthew Hampton (@matthewhampton)
  - The University of Virginia & early BPMN/DMN contributors
  - The BPMN.js team, Bruce Silver, and the wider open-source workflow community
  - Countless contributors past and present  

---

## License

m8flow is released under the **GNU Lesser General Public License (LGPL)**.