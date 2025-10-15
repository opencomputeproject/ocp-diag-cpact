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

Navigate to the project directory:
cd cpact

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
| `--schema_check`          | Specifies the mode of schema validation. Use scenario for validating scenario YAMLs.  |
|  `<test_yaml>`            | Path to the YAML file defining the test scenario to be validated or executed.         |
| `<schema_json>`           | Path to the JSON schema file used for validating the test YAML.                       |
| `--list`, `-l`                  | List all available test cases and exit without execution.                       |
| `--conn_config`           | Path to the connection configuration JSON file.                                       |
| `--discover_connections`, `-dc` | List all available connections without executing any tests.                     |
| `--list_scenarios_with_connections`, `-lsc` | List all scenarios with connections without                         |    execution.                                                                                                          |
| `--list_scenarios`, `ls` | List all scenarios without executing them.                                             |
| `run_with_discover_connections`, `-rdc` | Discover and check all connections without executing the tests.         |
| `run_with_schema_check`, `-rsc` | Execute tests with schema check.                                                |
| `--log-path`              | Set the log file or folder path to save execution logs.                               |

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


### 📂 Project Structure

| Component                | Description                                                                                           |
|---------------------------|-------------------------------------------------------------------------------------------------------|
| `BaseConnection`          | Abstract class defining the contract (`connect`, `execute_command`, `disconnect`) for all connections. |
| `SSHConnection`           | Manages SSH sessions. Supports sudo and robust command output parsing.                                |
| `RedfishConnection`       | Manages Redfish API sessions. Supports authenticated and unauthenticated access.                      |
| `TunnelConnection`        | Manages SSH tunnels to securely connect Redfish or SSH over a remote agent.                            |
| `ConnectionFactory`       | High-level manager to initialize, create, cache, check, execute, and disconnect all connections.       |
| `ssh_tunnel.py`           | Utility for setting up SSH tunnels (using `paramiko` or `sshpass`).                                   |
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
        "rackmanager_ssh_port": ,
        "rackmanager_redfish_port": ,
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

- Validation via Schema: YAML files are validated against a strict JSON Schema before execution.

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
|   ├── `schema_order_parser.py`      | Parses and manages the order of schema elements in scenario recipes.                        |
|   └── `step_widget.py`              | Widget for creating and editing individual scenario steps.                                  |
| `schema_checker/`         | Schema validation and YAML checking logic.                                                            |
|   ├── `base_schema.py`            | Defines base classes and utilities for schema validation.                                     |
|   ├── `schema_factory.py`         | Factory for loading and managing different schema types.                                      |
|   ├── `validate_config_schema.py` | Validates configuration YAML files against their schema.                                      |
|   └── `validate_scenario_schema.py`| Validates scenario YAML files against the scenario schema.                                   |
| `system_connections/`     | System and network connection handlers.                                                               |
|   ├── `base_connection.py`        | Abstract base class for all connection types.                                                 |
|   ├── `connection_discovery.py`   | Discovers available system connections.                                                       |
|   ├── `connection_factory.py`     | Factory for creating and managing connection instances.                                       |
|   ├── `constants.py`              | Contains constants used across connection modules.                                            |
|   ├── `local_connection.py`       | Implements local (on-host) connection logic.                                                  |
|   ├── `redfish_connection.py`     | Handles Redfish API-based remote connections.                                                 |
|   ├── `ssh_connection.py`         | Manages SSH-based remote connections.                                                         |
|   └── `tunnel_connection.py`      | Supports SSH tunneling for secure remote access.                                              |
| `utils/`                  | Utility functions and helpers.                                                                        |
|   ├── `docker_executor.py`        | Executes commands inside Docker containers.                                                   |  
|   ├── `docker_runner.py`          | Manages Docker container lifecycle for test execution.                                        |
|   ├── `logger_utils.py`           | Provides logging utilities and custom loggers.                                                |
|   ├── `matcher.py`                | Implements matching and validation logic for test outputs.                                    |
|   ├── `scenario_creator.py`       | Utility for programmatically creating test scenarios.                                         |
|   ├── `scenario_parser.py`        | Parses scenario YAML files into executable objects.                                           |
|   ├── `ssh_tunnel.py`             | Sets up and manages SSH tunnels.                                                              |
| `workspace/`              | Workspace management and related logic                                                                | 
| `main.py`                 | Entry point for initializing the application.                                                         |
| `spec`                    | Specifiaction and schema definations.                                                                 |  
| `tests`                   | Colletion on unit test and integration tests.                                                         |
| `.gitignore/`             | Git version control exclusions.                                                                       |
| `requirements.txt`        | Python dependencies to install.                                                                       |
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
pip install PyQt5
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
      continue:             # 🟡 (Optional) Whether to continue execution on failure.
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
#### 📦 Requirements
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
💡 Note : All dependencies are listed in requirements.txt. Install with pip install -r requirements.txt

```

## 📖 Documentation
## 📊 Roadmap

## 🤝 Contributing
## 🐛 Reporting Issues
## 📝 License
## 🙌 Acknowledgments
## 📬 Contact
