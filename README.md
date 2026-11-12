# 🚀 Project Name
  <pre> 
  ███████╗ ██████╗   █████╗   ██████╗ ████████╗
  ██╔════╝ ██╔══██╗ ██╔══██╗ ██╔════╝ ╚══██╔══╝
  ██║      ██████╔╝ ███████║ ██║         ██║   
  ██║      ██╔═══╝  ██╔══██║ ██║         ██║   
  ╚██████╗ ██║      ██║  ██║ ╚██████╗    ██║   
   ╚═════╝ ╚═╝      ╚═╝  ╚═╝  ╚═════╝    ╚═╝   
  
  <b>Ｃｌｏｕｄ－Ｐｒｏｃｅｓｓｏｒ－Ａｃｃｅｓｓｉｂｉｌｉｔｙ－Ｃｏｍｐｌｉａｎｃｅ－Ｔｏｏｌ </b> </pre>
  
## 📌 Description
``` 
This tool helps strengthen the CPU standardization effort meant for scaling across suppliers with focus on Debug, Telemetry, Impact-less FW updates. 
CPU Suppliers can run this tool to ensure that they meet the hyperscaler requirements on the above mentioned focus areas. 
https://github.com/MeritedHobbit/Cloud-Processor-Accessibility-Compliance-Tool.git
```

## ✨ Features
```
1. Spec-based compliance tooling architecture 
2. System connectivity support with multiple access methods – 
    a. In-Band (Linux Host)  
    b. Out-of-band (Redfish)
    c. Out-of-band (BMC)
    d. Inbuilt tunnel creation option (to bypass ,say, a Rack manager)
3. YAML based compliance scenario definitions 
    a. Internally leverages python
    b. Grouping of compliance scenarios per domain - like RAS, Debug, FWUpdate, Telemetry etc
    c. Yaml based scenario sequencing (along with expectations) 
    d. Dynamic compliance scenario discovery
        i. Connectivity based scenario listing
        ii. Filtered listing by domain/tag/group
        iii. Performance enhanced with scenario caching feature
6. Auto Documentation - Sphinx based documentation creation.
7. Logging & Report generation 
    a. CPACT Logs
    b. Workload logs 
    c. CPACT Reports
8. Schema validation and scoring
    a. Validates configuration and scenario files against JSON schema.
    b. Computes recipe-level scores across schema, map, and execution categories.
    c. Produces summary reporting and recipe score outputs.
    d. Supports nested scenario validation and child recipe aggregation.
    e. Records schema and map validation events in a unified scoring context.
    f. Uses a pluggable validation architecture for config vs scenario schema workflows.
```

## 🛠️ Installation
### **Prerequisites**
```
Before running this project, ensure you have the following installed:  

1. **Python 3.10+** – [Download Python](https://www.python.org/downloads/)  
2. **pip (Python package manager)** – Comes with Python, verify using:
   pip --version
```
### **Setup Instructions**
Follow these steps to set up and run the project:

#### 1️⃣ **Clone the Repository**  
Use SSH to securely clone the repository:  
```sh
git clone git@github.com:your-username/your-repo.git

```
#### 2️⃣ **Set Up a Virtual Environment**
```
For Linux/Mac:
python3 -m venv venv && source venv/bin/activate

For Windows:
python -m venv venv && venv\Scripts\activate
```

#### 3️⃣ **Install Required Packages**
```
pip install -r requirements.txt
For the scenario recipe creator GUI (-rsc) as well:
pip install -r requirements-gui.txt
To verify installed packages:
pip list
```

## 🛡️ Compliance Scenarios
## 🚀 Usage
### Run the Application
### 🧩 Command Line Options

The framework extends `python` to support **custom command-line options** for flexible test case selection, listing, and configuration.

You can run test cases using various filters like test ID, test name, group, tag, or folder.

### Available Options

| Option                    | Description                                                                           |
|---------------------------|-------------------------------------------------------------------------------------- |
| `--test_id`               | Run test case(s) by Test Case ID(s) (comma-separated).                                |
| `--test_name`             | Run test case(s) by Test Case Name(s) (comma-separated).                              |
| `--test_group`            | Run test case(s) by Test Group(s) (comma-separated).                                  |
| `--tags`                  | Run test case(s) by Tag(s) (comma-separated).                                         |
| `--test_dir`              | Path to the directory containing input test definitions or scenarios.                 |
| `--workspace`             | Path to the workspace where logs, temporary files, and results will be stored.        |
| `--log_override`          | Manual override for the output log folder. Logs/results are written directly into this folder (no `test_run_<timestamp>` sub-folder). The folder is reused if it exists, otherwise it is created. |
| `--allowed_path`          | Extra folder that recipe file paths may point into (repeatable). See *Recipe path and analysis limits* below. |
| `--run_all_scenarios`     | Run All scenarios.                                                                    |
| `--run_scenario_creator`  | Run scenario creator GUI.                                                             |
| `--run_with_schema_check` | Validate recipes (and nested recipes/map files) before running them. This is the default. |
| `--no-schema-check`       | Skip schema validation while running recipes; the Schema/Map score categories show N/A. |
| `--historical_data`       | Option to provide the historical data. Like previously ran recipe results.            |
| `--schema_check`          | Specifies the mode of schema validation. Use scenario for validating scenario YAMLs.  |
|  `<test_yaml>`            | Path to the YAML file defining the test scenario to be validated or executed.         |
| `<schema_json>`           | Path to the JSON schema file used for validating the test YAML.                       |
| `--list`, `-l`                  | List all available test cases and exit without execution.                       |
| `--conn_config`           | Path to the connection configuration JSON file.                                       |
| `--discover_connections`, `-dc` | List all available connections without executing any tests.                     |
| `--list_scenarios_with_connections`, `-lsc` | List all scenarios with connections without                         |    execution.                                                                                                          |
| `--list_scenarios`, `ls` | List all scenarios without executing them.                                             |
| `run_with_discover_connections`, `-rdc` | Discover and check all connections without executing the tests.         |
| `--log-path`              | Set the log file or folder path to save execution logs.                               |

### 🔒 Recipe path and analysis limits

- **Recipe file paths** (`log_analysis_path`, `expected_output_path`, `scenario_path`, `map_file`) must resolve (after `..` and symlinks) inside an allowed folder, otherwise the step or recipe fails. Allowed by default: the working directory, `--workspace`, `--test_dir`, the run's log folder and the folder of the recipe that references the path. Add more with `--allowed_path DIR` (repeatable) or the `CPACT_ALLOWED_PATHS` environment variable (`os.pathsep`-separated), e.g. `--allowed_path /var/log`.
- **Recipe regexes** (diagnostic/output analysis, `expected_output`, JSON patterns) are limited to 4096 characters; patterns with nested quantifiers such as `(a+)+` log a warning, and slow matches (>5 s) are logged. Inputs larger than 256 MB fail the step instead of being truncated; raise the limit with `CPACT_MAX_ANALYSIS_MB`.

---

### 🛠 Example Usage

- **Run All Test Cases from the complete Project**
  ```
  python main.py
  ```
- **List All Test Cases**
  ```
  python main.py --list
  ```
- **List Test Cases with Filters (Group, Tag)**
  ```
  python main.py --list --test_group "<test_group>"
  python main.py --list --tags "<tags>"
  ```
- **List Test Cases with Available Connections**
  ```
  python main.py --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace --list_scenarios_with_connections
  ```
- **List all Available Connections**
  ```
  python main.py --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace --run_with_discover_connections
  ```
- **Run by Test Case ID**
  ```
  python main.py --test_id "<test_id>" --conn_config ..\path\to\config_file --workspace ..\path\to\workspace
  ```
- **Run by Test Case Group**
  ```
  python main.py --test_group "<test_group>" --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace
  ```
- **Run by Test Case Name** 
  ```
  python main.py --test_name "<test_name>" --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace
  ```
- **Run by Test Case Tag**
  ```
  python main.py --tags "<tag_name>" --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace
  ```
- **Run All Testcases from a directory**
  ```
  python main.py --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --workspace ..\path\to\workspace
  ```
- **Run Testcases with schema_check_scenario**
  ```
  python main.py --test_dir ..\path\to\tests --workspace ..\path\to\workspace --schema_check scenario ..\path\to\YAML_schema ..\path\to\schema_recipe.json <schema_recipe_.jsonfile>
  ```

  - **Run all scenarios**
  ```
  python main.py --test_dir ..\path\to\tests --workspace ..\path\to\workspace --conn_config ..\path\to\config_file --run_all_scenarios
  ```

  - **Write logs to a fixed (override) folder**
  ```
  mkdir .\logs\CPACT
  python main.py --test_dir ..\path\to\tests --conn_config ..\path\to\config_file --log_override .\logs\CPACT
  ```
  Logs (`test_run.log`) and result JSON files are written directly into `.\logs\CPACT`. Re-running with the same folder reuses it (the log file is appended to and result files are overwritten); if the folder does not exist it is created.

## 📡 Connection Management

This module provides a **unified framework** for managing different types of remote connections — **SSH**, **Redfish**, and **Tunneled connections** — in a highly flexible, extensible, and reusable way.  
It simplifies connection handling, command execution, and session management across direct and tunneled paths, all driven via a structured **JSON configuration**.

### 🚀 Key Features

- **Supports multiple connection types**:  
  - SSH connections (using `paramiko`)
  - Redfish REST API connections (using `redfish` library)
  - SSH Tunnel connections (local port forwarding)
- **Single configuration file** (`config.json`) to manage all connection details.
- **Automatic connection management**: connect, execute, and disconnect seamlessly.
- **Error handling and detection**: Predefined patterns to catch command execution errors.
- **Pretty logging**: Tabular view of connection status using `prettytable` and colorful output using `colorama`.
- **Sudo support**: For executing privileged SSH commands.
- **Redfish Session Authentication**: Optional support for authenticated Redfish sessions.
- **Tunneling Support**: Allows Redfish and SSH access over an SSH Tunnel when direct access is not possible.
- **Extensible Architecture**: Abstract base class (`BaseConnection`) to easily add new connection types if needed.
- **Caching**: Established connections are cached to avoid redundant reconnections.


## 🔍 Schema Validation Architecture
- Schema validation is implemented through the `cpact.schema_checker` subsystem.
- The public API is `SchemaService.validate(request)`.
- `SchemaValidator` orchestrates schema processing by:
  - loading YAML scenario or config sources,
  - resolving the `schema_version` from the scenario metadata,
  - selecting the right validator using `ExecutorFactory`, and
  - validating scenario schema and optional map schema files.
- `ValidationRequest` includes:
  - `schema_type`: `config` or `scenario`
  - `source`: a path or list of paths to validate
  - `schema_file`: optional explicit schema definition file
- Scenario validation uses `ScenarioSchemaValidator`, which:
  - detects duplicate YAML keys,
  - loads YAML with `ruamel.yaml`,
  - validates the document against Draft7 JSON Schema, and
  - validates the referenced `map_file` when present.
- The schema output model includes:
  - `SchemaValidationResult` for each recipe,
  - `ValidationResult` for aggregated success/failure counts.
- Use the `schema_version` field in a scenario YAML to select the schema directory under `spec/schema/`.

## 🧮 Scoring Architecture
- Scoring is implemented in the `cpact.scoring` subsystem.
- `ScoreManager` is a thread-safe singleton that coordinates all score tracking.
- Each recipe execution is represented by a `ScoreContext`, which tracks:
  - schema and map validation state,
  - execution step counts,
  - profile bonus scores,
  - nested recipe parent/child relationships.
- Scoring events include:
  - `SCHEMA_VALIDATION`,
  - `MAP_VALIDATION`,
  - `EXECUTION_STEP`,
  - `PROFILE_SCORE`, and
  - `NESTED_RECIPE`.
- `record_schema_validation()` converts a validation result into schema/map scoring events.
- `calculate(execution_id)` produces normalized category scores using:
  - Schema weight,
  - Map weight, and
  - Execution weight.
- Category scores are represented with `CategoryScore` objects and the final result with `ScoreResult`.
- `ScorePrinter` renders score summaries, recipe status, and execution statistics.
- Nested scenario support is built with `start_nested_run()`, which links child recipes to their parent execution.

## ✅ What to Use
- Use `--schema_check scenario <file_or_dir> [schema_file]` for explicit scenario validation.
- Use `--schema_check config <file_or_dir> [schema_file]` to validate config payloads.
- Use `--run_with_schema_check` to enable schema validation when executing recipes.
- Use `--no-schema-check` to skip schema validation entirely.
- Use `schema_version` inside recipes to choose the correct schema version.
- Use `map_file` in recipes to validate associated map definitions as part of the scoring pipeline.
- Place schema definitions under `spec/schema/` and omit `schema_file` to resolve defaults automatically.

### 📂 Project Structure

| Component                | Description                                                                                           |
|---------------------------|-------------------------------------------------------------------------------------------------------|
| `BaseConnection`          | Abstract class defining the contract (`connect`, `execute_command`, `disconnect`) for all connections. |
| `SSHConnection`           | Manages SSH sessions. Supports sudo and robust command output parsing.                                |
| `RedfishConnection`       | Manages Redfish API sessions. Supports authenticated and unauthenticated access.                      |
| `TunnelConnection`        | Manages SSH tunnels to securely connect Redfish or SSH over a remote agent.                            |
| `ConnectionFactory`       | High-level manager to initialize, create, cache, check, execute, and disconnect all connections.       |
| `logger_utils.py`         | Logger setup with custom formatting for all modules.                                                  |

---
### 🧩 Architecture Diagram
![alt text](image.png)

### 🛠️ How to Use
___

#### 1. Create a JSON Configuration File

Define your connection details (hosts, ports, credentials, tunnel settings, etc.).  
Example snippet:

```json
{
    "Connection": {
        "redfish_port": 8080,
        "protocol": "https",
        "use_ssl":true,
        "verify_ssl": true,
        "ca_bundle": "",
        "connections": [
        ],
        "connection_types": [
            "ssh",
            "redfish"
        ]
    },
    "Inband": {
        "inband_host": "",
        "inband_ssh_port": 22,
        "inband_username": "",
        "inband_password": ""
    },
    "RackManager": {
        "rackmanager_host": "",
        "rackmanager_ssh_port": 22,
        "rackmanager_redfish_port": 443,
        "rackmanager_username": "",
        "rackmanager_password": "",
        "rackmanager_redfish_auth": true
    },
    "NodeManager": {
        "nodemanager_tunnel": true,
        "nodemanager_host": "",
        "nodemanager_redfish_port": 443,
        "nodemanager_ssh_port": 22,
        "nodemanager_username": "",
        "nodemanager_password": "",
        "nodemanager_redfish_auth": false
    },
    "NodeManagerTunnel": {
        "nodemanager_tunnel_agent": "",
        "nodemanager_tunnel_local_host": "127.0.0.1",
        "nodemanager_tunnel_ssh_local_port": [1234],
        "nodemanager_tunnel_redfish_local_port": [5555]
    }
}
```

**TLS and host-key verification**

- Redfish verifies the server's TLS certificate by default. Set `Connection.ca_bundle` (or a per-section `<prefix>_ca_bundle`, e.g. `rackmanager_ca_bundle`) to a PEM file to trust a private/self-signed CA. Set `verify_ssl: false` (globally or per section, e.g. `nodemanager_verify_ssl`) only for isolated lab setups; a warning is logged. Tunneled Redfish verifies the certificate against `nodemanager_host`, not the local tunnel address.
- SSH connections and SSH tunnels only connect to hosts whose key is already in `~/.ssh/known_hosts` (or the configured known_hosts file). For tunnel agents (jump hosts) set `tunnel_agent_known_hosts_file` on the `NodeManagerTunnel` section, or `<agent>_known_hosts_file` on the legacy agent section. Add keys after verifying them out-of-band, e.g. `ssh-keyscan -p 22 <host> >> ~/.ssh/known_hosts`.
- SSH commands on targets with a POSIX shell are prefixed with `echo <marker>$$;` so CPACT can kill the remote process group when a step exceeds its `duration` (synchronous steps) or a background (`continue: true`) task times out or is terminated. CPACT detects a POSIX shell with a one-time probe per connection, so vendor CLIs (e.g. a RackManager shell) are left untouched; force it with `<prefix>_track_remote_pid: true` / `false`. Privileged (`use_sudo`) commands run in an elevated PTY shell instead, where a timeout sends Ctrl+C.

#### 2. Initialize and Connect
```
from connection_factory import ConnectionFactory

ConnectionFactory.initialize("path/to/config.json")
connections = ConnectionFactory.get_connections()
ConnectionFactory.check_connections(connections)
```
#### 3. Execute Commands
```
output = ConnectionFactory.execute_command(connections, "NodeManager", "ssh", "ls /tmp", use_sudo=False)
print(output)

redfish_response = ConnectionFactory.execute_command(connections, "NodeManager", "redfish", "/redfish/v1/Systems")
print(redfish_response.dict)

```
#### 4. Disconnect All
```
ConnectionFactory.disconnect_all(connections)
```
#### 📚 Requirements
- paramiko

- redfish

- prettytable

- colorama

- Standard Python libraries (logging, json, re, time)


## ✨ Features 
### 🧪 Test Case Execution Framework
This framework enables data-driven testing by defining test cases in YAML files and executing them automatically through structured test steps.
It supports SSH, Redfish API, and command validation mechanisms to ensure reliable test automation for system-level and API-level validation.
### 🚀 Key Features
___

- YAML-Based Test Cases: Define all test cases declaratively using YAML files for easy versioning and editing.

- Multi-Step Execution: Each test case can consist of one or multiple sequential steps.

- Flexible Command Execution: Supports SSH commands and Redfish REST API operations.

- Output Validation: Supports output verification using:

- JSON structure validation

- Text matching

- Regex-based matching

- Exact string matching

- Detailed Logging: Each step and case execution is logged with success/failure status, durations, and rich summaries.

- Failure Aggregation: Collects all failures for consolidated reporting at the end of test runs.

- Caching Support: Caches loaded test cases for faster reloads using .cache folder.

- Validation via Schema: YAML and configuration files are validated against JSON Schema before execution.

- Scoring and Reporting: Recipe-level scores are calculated for schema, map, and execution outcomes, with summary reports and nested recipe aggregation.

### 🗂️ Project Structure
___
| File/Folder                   | Description                                                                                       |
|-------------------------------|---------------------------------------------------------------------------------------------------|
| `analysis/`               | Folder containing modules for analyzing test results and data.                                        |
|   ├── `analysis_factory.py`    | Factory for creating appropriate analysis objects dynamically.                                   | 
|   ├── `base_analysis.py`       | Defines the abstract base class for all analysis types.                                          |
|   ├── `diagnostic_analysis.py` | Implements logic for diagnostic data analysis and error detection.                               |
|   ├── `output_analysis.py`     | Handles output validation and analysis for test steps.                                           |              
| `core/`                   | Core modules for managing connections, test cases, steps, logging, etc.                               |
| 	├── `context.py`            | Manages shared context and state for scenario execution.                                          |
| 	├── `orchestrator.py`       | Coordinates the overall execution flow of scenarios.                                              |
| 	├── `scenario_runner.py`    | Handles running individual test scenarios.                                                        |  
| 	└── `step_executor.py`      | Executes individual steps within a test scenario.                                                 |
| `executor/`               | Holds code for executing the scenarios and commands.                                                  |
|   ├── `base_executor.py`      | Defines base classes and interfaces for executors.                                                |
|   ├── `command_executor.py`   | Executes shell or SSH commands as part of test steps.                                             |
|   ├── `executor_factory.py`   | Factory for creating and managing executor instances.                                             |
|   ├── `log_analyzer.py`       | Analyzes logs generated during scenario execution.                                                |
|   └── `scenario_invoker.py`   | Invokes and manages the execution of test scenarios.                                              |
| `expression/`             | Expression parsing and evaluation utilities.                                                          |
|   ├──`evaluator.py`           | Provides functionality to evaluate logical and comparison expressions for scenario entry criteria.|
| `result_builder/`         | Builds and format result outputs.                                                                     |
|   ├──`result_builder.py`      | Collects, manages, and summarizes test step results and diagnostics during scenario execution.    |
| `scenario_recipe_creator/`| Includes tools for creating and managing scenario recipes.                                            |
|   ├── `constants.py`                | Defines UI constants, styles, and utility widgets for the scenario recipe creator.          |
|   ├── `diagnostic_analysis_widget.py`| Provides a widget for configuring diagnostic analysis steps in scenarios.                  |
|   ├── `docker_widget.py`            | Implements a widget for managing Docker-related scenario settings.                          |
|   ├── `entry_criteria_widget.py`    | Widget for defining and editing scenario entry criteria.                                    |
|   ├── `output_analysis_widget.py`   | Widget for specifying and displaying output analysis configuration.                         | 
|   ├── `recipe_create_widget.py`     | Main widget for creating and editing scenario recipes.                                      |
|   ├── `scenario_creator.py`         | Core logic for building and managing scenario recipes.                                      |
|   ├── `recipe_serialization.py`     | Qt-free sanitizing/normalizing of recipe data for export.                                   |
|   ├── `autosave_store.py`           | Qt-free autosave files (unique per window, atomic writes, pruning).                         |
|   ├── `schema_order_parser.py`      | Parses and manages the order of schema elements in scenario recipes.                        |
|   └── `step_widget.py`              | Widget for creating and editing individual scenario steps.                                  |
| `schema_checker/`         | Schema validation and YAML checking logic.                                                            |
|   ├── `base_schema.py`            | Defines base classes and utilities for schema validation.                                     |
|   ├── `schema_service.py`         | Entry point that runs schema validation and reporting.                                        |
|   ├── `factories/schema_factory.py` | Factory for selecting the validator for each schema type.                                   |
|   ├── `validators/schema_validator.py` | Resolves the schema version/file and dispatches validation.                              |
|   ├── `validators/validate_config_schema.py` | Validates configuration files against their schema.                                |
|   └── `validators/validate_scenario_schema.py`| Validates scenario YAML files (and their map files) against the scenario schema.  |
| `system_connections/`     | System and network connection handlers.                                                               |
|   ├── `base_connection.py`        | Abstract base class for all connection types.                                                 |
|   ├── `connection_discovery.py`   | Discovers available system connections.                                                       |
|   ├── `connection_factory.py`     | Factory for creating and managing connection instances.                                       |
|   ├── `constants.py`              | Contains constants used across connection modules.                                            |
|   ├── `local_connection.py`       | Implements local (on-host) connection logic.                                                  |
|   ├── `redfish_connection.py`     | Handles Redfish API-based remote connections.                                                 |
|   ├── `ssh_connection.py`         | Manages SSH-based remote connections.                                                         |
|   ├── `ssh_tasks.py`              | Background-task lifecycle for SSH connections (start, wait, terminate, cleanup).              |
|   └── `tunnel_connection.py`      | Supports SSH tunneling for secure remote access.                                              |
| `utils/`                  | Utility functions and helpers.                                                                        |
|   ├── `docker_executor.py`        | Executes commands inside Docker containers.                                                   |  
|   ├── `logger_utils.py`           | Provides logging utilities and custom loggers.                                                |
|   ├── `redaction.py`              | Masks passwords/tokens in log records and OCP TV output.                                      |
|   ├── `matcher.py`                | Implements matching and validation logic for test outputs.                                    |
|   ├── `scenario_creator.py`       | Utility for programmatically creating test scenarios.                                         |
|   ├── `scenario_parser.py`        | Parses scenario YAML files into executable objects.                                           |
|   ├── `path_guard.py`             | Confines recipe file paths to the allowed folders; safe file names.                           |
|   ├── `regex_guard.py`            | Length/size limits and slow-match logging for recipe regexes.                                 |
|   ├── `json_validator.py`         | Validate json regex                                                                           |
| `workspace/`              | Workspace management and related logic                                                                | 
| `main.py`                 | Entry point for initializing the application.                                                         |
| `cpact/test_discovery.py` | Recipe discovery and listing for the CLI.                                                             |
| `cpact/connection_checks.py` | Connection discovery and statistics (`--discover_connections`).                                    |
| `cpact/recipe_validation.py` | Schema checks (`--schema_check`) and pre-run validation of recipes and nested recipes.             |
| `spec`                    | Specifiaction and schema definations.                                                                 |  
| `tests`                   | Colletion on unit test and integration tests.                                                         |
| `.gitignore/`             | Git version control exclusions.                                                                       |
| `requirements.txt`        | Python dependencies to install.                                                                       |
| `requirements-gui.txt`    | Adds PyQt5 for the scenario recipe creator GUI (`-rsc`).                                              |
| `README.md`               | Project documentation.                                                                                |

## 🛠️ How It Works
## 📝 Scenario Schema
The scenario schema used for validating YAML test definitions is located at:

📄 **Schema Path:**

[Scenario Recipe Schema](https://github.com/MeritedHobbit/Cloud-Processor-Accessibility-Compliance-Tool/tree/main/spec/schema/scenario_recipe_schema_0.7.json)

### ✅ Example Usage with Schema Check
```
python main.py --test_dir ../path/to/tests \
               --workspace ../path/to/workspace \
               --schema_check scenario \
               ../spec/schema/scenario_recipe_schema_0.7.json \
               ../path/to/scenario_recipe.json
```
### 💡Note: This command will validate your scenario YAMLs against the schema located at spec/scenario_schema.json and execute them accordingly.

## Usage of scenario_creator:
The scenario_creator.py script provides a PyQt5-based graphical interface for designing scenario recipes interactively using a JSON schema.

### ✨ Features
- Dynamic form generation from JSON schema
- Modern UI with high-DPI and accessibility support
- Soft card shadows and polished layout
- Windows-specific taskbar grouping
- Integrated with RecipeCreator widget for scenario building

### 🚀 How to Launch
```
python scenario_recipe_creator/scenario_creator.py
```
This opens the Scenario Designer window. Select a JSON schema file (e.g. [Scenario Recipe Schema](https://github.com/MeritedHobbit/Cloud-Processor-Accessibility-Compliance-Tool/tree/main/spec/schema/scenario_recipe_schema_0.7.json)) and begin building your scenario recipe using the GUI.
### 🛠 Requirements
```
pip install -r requirements-gui.txt
```
### 💡Note: Ensure the following modules are available:
- constants.py
- recipe_create_widget.py

### 📂 Output
Once the schema is loaded, the tool launches the RecipeCreator widget, allowing you to build and save scenario recipes in YAML format. These recipes can then be executed using:
```
python main.py --schema_check scenario spec/schema/scenario_recipe_schema_0.7.json path/to/your_recipe.yaml
```
### 📄 YAML Recipe for the schema
```
test_scenario:              # ✅ (Mandatory) Defines a complete test case, including its steps and execution details
  test_id:                  # ✅ (Mandatory) Unique id for the test 
  test_name:                # ✅ (Mandatory) Unique name for the test
  test_group:               # ✅ (Mandatory) Unique group name the test belongs to
  tags:                     # 🟡 (Optional) tag value of test
    -

  docker:                   # 🟡 (Optional) Container Configuration step
    - container_name:       # ✅ (Mandatory) Name of the container 
      container_image:      # ✅ (Mandatory) Image name for the container
      shell:                # 🟡 (Optional) Specifies the default shell to use inside the Docker container during test execution.
      container_location:   # 🟡 (Optional) "local" or "remote"
      connection_type:      # ✅ (Mandatory) "Local" | "Inband" | "RackManager" | "NodeManager"
      connection:           # ✅ (Mandatory) "local" | "redfish" | "ssh"
      use_sudo:             # 🟡 Boolean flag

  test_steps:               # ✅ (Mandatory) Test steps to be executed
  ```
  > ℹ️ `connection` and `connection_type` values (and `Connection.connections` / `Connection.connection_types` in config files) are validated case-insensitively, e.g. `rackmanager` or `SSH` are accepted. All other fields remain case-sensitive.

  ### command_execution step
  ```
    - step_id:              # ✅ (Mandatory) Unique step_id value
      step_name:            # ✅ (Mandatory) Unique step_name
      step_description:     # 🟡 (Optional) field summarizing step details.
      connection_type:      # ✅ (Mandatory) Type of connection to use (e.g., Local, Inband, RackManager, NodeManager).
      connection:           # ✅ (Mandatory) Connection method (e.g., local, redfish, ssh).
      step_type:            # ✅ (Mandatory) Type of step (e.g., command_execution, log_analysis, invoke_scenario).
      step_command:         # ✅ (Mandatory for command_execution) Command to execute in this step.
      validator_type:       # ✅ (Mandatory) Type of validation to apply to the step output.
      
      use_sudo:             # 🟡 (Optional) Whether to use sudo for command execution.
      method:               # 🟡 (Optional) HTTP method for API calls (e.g., GET, POST).
      headers:              # 🟡 (Optional) HTTP headers for API calls.
      body:                 # 🟡 (Optional) HTTP request body for API calls.
      duration:             # 🟡 (Optional) Maximum duration (in seconds) to allow for this step.
      continue:             # 🟡 (Optional) Run the command in the background and validate it when the scenario ends. It must exit 0 within `duration` seconds of validation starting (otherwise it is stopped and the step fails); allow expected codes yourself, e.g. `timeout 120 ./tool || [ $? -eq 124 ]`.
      loop:                 # 🟡 (Optional) Number of times to repeat this step.
      expected_output:      # 🟡 (Optional) Expected output string for validation.
      expected_output_path: # 🟡 (Optional) Path to a file containing expected output.
      output_analysis:      # 🟡 (Optional) List of regex patterns and parameters for output analysis.
        - regex:            # ✅ (Mandatory if output_analysis is used) Regex pattern to match in the output.
          parameter_to_set: # ✅ (Mandatory if output_analysis is used) Parameter to set if regex matches.
      entry_criteria:       # 🟡 (Optional) List of conditions that must be met before executing the step.
        - expression:       # ✅ (Mandatory if entry_criteria is used) Logical expression to evaluate entry criteria.
          entry_criteria_note: # 🟡 (Optional) Note or description for the entry criteria.

  ```
  ### log_analysis step
  ```
    - step_id:              # ✅ (Mandatory) Unique step_id value
      step_name:            # ✅ (Mandatory) Unique step_name
      step_description:     # 🟡 (Optional) field summarizing step details.
      connection_type:      # ✅ (Mandatory) Type of connection to use (e.g., Local, Inband, RackManager, NodeManager).
      connection:           # ✅ (Mandatory) Connection method (e.g., local, redfish, ssh).
      step_type:            # ✅ (Mandatory) log_analysis- Type of step (e.g., command_execution, log_analysis, invoke_scenario).
      log_analysis_path:    # ✅ (Mandatory for log_analysis) Path to the log file to be analyzed.
      validator_type:       # ✅ (Mandatory) Type of validation to apply to the step output.

      diagnostic_analysis:        # 🟡 (Optional) List of diagnostic patterns and parameters for log analysis.
        - search_string:          # ✅ (Mandatory in one diagnostic_analysis form) String to search for in the log.
          diagnostic_result_code: # ✅ (Mandatory with search_string) Result code to set if search_string matches.
          parameter_to_set:       # 🟡 (Optional) Parameter to set if search_string matches.
        - diagnostic_search_string: # ✅ (Mandatory in alternate diagnostic_analysis form) Diagnostic search pattern.
          parameter_to_set:       # ✅ (Mandatory with diagnostic_search_string) Parameter to set if pattern matches.
  ```
  ### invoke_scenario step
  ```
    - step_id:              # ✅ (Mandatory) Unique step_id value
      step_name:            # ✅ (Mandatory) Unique step_name
      step_description:     # 🟡 (Optional) field summarizing step details.
      connection_type:      # ✅ (Mandatory) Type of connection to use (e.g., Local, Inband, RackManager, NodeManager).
      connection:           # ✅ (Mandatory) Connection method (e.g., local, redfish, ssh).
      step_type:            # ✅ (Mandatory) invoke_scenario- Type of step (e.g., command_execution, log_analysis, invoke_scenario).
      entry_criteria:       # 🟡 (Optional) List of conditions that must be met before executing the step.
        - expression:       # ✅ (Mandatory if entry_criteria is used) Logical expression to evaluate entry criteria.
          entry_criteria_note: # 🟡 (Optional) Note or description for the entry criteria.

      scenario_path:        # ✅ (Mandatory for invoke_scenario) Path to another scenario YAML to invoke.
```
### 🔹 Schema Selection
```
- The `schema_version` field allows a scenario YAML to explicitly specify which JSON schema version should be used for validation.
- The framework attempts to load the corresponding schema file from the `spec/schema/` directory.
- If the specified schema version is not found, the framework automatically falls back to the latest available schema version.

  test_scenario:
    test_id: <>test_id_name>
    test_name: <test_name>
    test_group: <test_groupiag>
    schema_version: <schema_version>

```
### 📂 Paths Block
```
- The `paths` block defines all filesystem locations used by the framework, such as workspace directories, logs, map files, and scenario locations.
- Each entry under `paths` becomes a reusable named placeholder that can be referenced anywhere in the YAML using `{placeholder_name}` syntax.
- This helps avoid hardcoding paths and keeps scenarios clean, portable, and easy to maintain.
- If a path value is absolute, it is used as-is.
- If a path value is relative, it is resolved relative to the directory containing the scenario YAML file.

  paths:
    workspace_path: ./sample_workspace
    scenario_path: ./tests
-
```
### 🏷️ Parameters Block (schema 0.8)
```
- The `parameters` block defines named values that are NOT filesystem paths, e.g. IP addresses,
  image tags, device names or counts, so you can refer to them by a friendly name.
- Reference a param anywhere in the recipe with `{param:name}` or simply `{name}`.
- Values may be a string, number, boolean or a nested group of parameters.
- Reach into a group with `.` or `->` (they are interchangeable and can be mixed):
  `{param:server.ip}`, `{param:server->ip}`, `{server.creds->user}`.
- A param value may itself use `{env:VAR}`, `{path_name}` and other parameters (including nested
  ones), in any declaration order.
- Names at every level must match `^[A-Za-z_][A-Za-z0-9_]*$`. Top-level names must not be
  `env` or `param`, and must not duplicate a name in `paths` (a duplicate is ignored and an
  error is logged).
- Use parameters in string fields; typed fields such as `use_sudo` (boolean) are schema-checked
  before substitution. A whole group can only be used as a complete value (e.g.
  `body: '{param:server}'`), not inside text.

  test_scenario:
    schema_version: '0.8'
    paths:
      workspace_path: ./sample_workspace
    parameters:
      image: shc_gnr_test:1.4.4
      bmc:
        ip: 192.168.4.1
        port: 5000
      banner: '{param:image} from {workspace_path}'
    test_steps:
    - step_id: step_001
      step_command: docker pull {param:bmc.ip}:{bmc->port}/{image} && echo {banner}
```
### 🗺️ Map File
```
- The map file defines how the framework interprets log output and diagnostic results.
- It maps plain-text or regular-expression search patterns to logical identifiers (virtual IDs) and Diagnostic Result Codes (DRCs).
- During log-analysis or diagnostic steps, matched patterns are translated into structured results using the map file.
- The map file path can reference placeholders defined in the `paths` block for better portability and reuse.
 
  test_scenario:
    map_file: '{workspace_path}/map_file.json'
    paths:
      workspace_path: ./sample_workspace

```
### 📦 Requirements
___
- Python 3.10 0r Higher Version

- PyYAML

- jsonschema

- paramiko

- redfish

- prettytable

- colorama

- PyQt5

- docker

```
💡 Note : All dependencies are pinned in requirements.txt (CLI) and requirements-gui.txt (adds PyQt5 for the GUI). Install with pip install -r requirements.txt (or -r requirements-gui.txt for both)

```

## 📖 Documentation
## 📊 Roadmap

## 🤝 Contributing
## 🐛 Reporting Issues
## 📝 License
## 🙌 Acknowledgments
## 📬 Contact
