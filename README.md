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
CPU Suppliers can run this tool to ensure that they meet the cloud scale requirements on the mentioned focus areas. 
https://github.com/MeritedHobbit/Cloud-Processor-Accessibility-Compliance-Tool.git
```
## ✨ Features
```
1. Spec-based compliance tooling
2. A Spec decides compliance scenario pass/fail
3. Spec is permitted to be flexible
4. Multiple access methods – 
    a. In-Band (Linux Host)  
    b. Out-of-band (Redfish)
    c. Out-of-band (BMC)
    d. Inbuilt tunnel creation option (to bypass ,say, RackSCM)
5. Pytest based compliance scenario definitions 
6. Grouping of tests per domain 
7. Yaml based test sequencing (along with expectations) 
8. Auto Documentation
9. Logging & Report generation 
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
```
🔹List all test cases
  pytest --list-tests

🔹List all test cases with yaml
  pytest --list-test --testdata /path/to/test.yaml

🔹Run All Tests
  pytest

🔹Run All Tests with yaml
  pytest --testdata /path/to/test.yaml

🔹Run Tests using test names
    pytest cpact.py --key "test_name_1" "test_name_2" --config //path/to/config.ini

🔹Run Tests using test names with yaml tests also 
    pytest cpact.py --key "test_name_1" "test_name_2" --config //path/to/config.ini --testdata /path/to/test.yaml

🔹Run Tests using test id
    pytest cpact.py --key "test_id_1" "test_id_2" --config //path/to/config.ini

🔹Run Tests using test id with yaml tests also 
    pytest cpact.py --key "test_id_1" "test_id_2" --config //path/to/config.ini --testdata /path/to/test.yaml

```

## ⚙️ Configuration  

CPACT provides flexible configuration options to customize its behavior.  

---

### 1️⃣ **Using a Configuration File**  
CPACT supports configuration via a `.env` file  

#### 📄 **Example `.env` File**  
Create a `.env` file in the root directory and add:  
```ini
[Connection]
tunnel=True
redfish_port = 
protocol=https
connection_type=[ssh, redfish]
redfish_auth=false

[Target]
target_host = 
target_port = 
target_username=
target_password=

[SSH]
ssh_host = 
ssh_port = 
ssh_username = 
ssh_password = 

[Tunnel]
local_host = 127.0.0.1
local_port = [5555, 9999]


[Validator]
tags=
names_ids=
log_dir=./logs
console_log=True
debug=True


redfish_uris=./workspace/redfish_uri.json

```
## ✨ Features 
### 1️⃣ **Using a YAML File to run test cases**
```
test_case_1:
  test_id: "TC_001"
  test_name: "Test Case 1"
  test_group: "Group 1"
  test_steps:
    - command: 
      use_sudo: false
      connection_type: ssh
      validate_type: text_regex
      expected_output:
test_case_2:
  test_id: "TC_002"
  test_name: "Test Case 2"
  test_group: "Group 2"
  test_steps:
    - command: 
      use_sudo: false
      connection_type: ssh
      validate_type: text_regex
      expected_output:
```
## 📖 Documentation
## 📊 Roadmap

## 🤝 Contributing
## 🐛 Reporting Issues
## 📝 License
## 🙌 Acknowledgments
## 📬 Contact
