"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""
from  sshtunnel import SSHTunnelForwarder, HandlerSSHTunnelForwarderError
import subprocess
import os
from abc import ABC, abstractmethod

class SSHTunnel(ABC):
    """
    SSHTunnel is an abstract base class that provides a blueprint for creating, managing, 
    and terminating SSH tunnels. It is designed to be extended by subclasses that implement 
    the abstract methods for specific SSH tunneling functionality.
    Attributes:
        test_info_logger (Logger): A logger instance used for logging information related to the SSH tunnel.
        ssh_tunnel (object): A placeholder for the SSH tunnel instance. This should be initialized by subclasses.
        binded_port (int): The local port bound to the SSH tunnel. This should be set by subclasses.
    Methods:
        create_tunnel(local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Abstract method to create an SSH tunnel. Must be implemented by subclasses.
        setup_ssh_tunnel(local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Abstract method to set up the SSH tunnel. Must be implemented by subclasses.
        kill_ssh_tunnel():
            Abstract method to terminate the SSH tunnel. Must be implemented by subclasses.
    """
    
    def __init__(self, logger) -> None:
        self.test_info_logger = logger
        self.ssh_tunnel = None
        self.binded_port = None

    @abstractmethod
    def create_tunnel(self, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
        pass

    @abstractmethod
    def setup_ssh_tunnel(self, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
        pass

    @abstractmethod
    def kill_ssh_tunnel(self):
        pass

class SSHTunnelWithLibrary(SSHTunnel):
    """
    A class to manage SSH tunneling using the SSHTunnelForwarder library.
    This class provides methods to create, set up, and terminate SSH tunnels
    for secure communication between a local machine and a remote host.
    Methods:
        create_tunnel(local_host, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Creates an SSH tunnel using the SSHTunnelForwarder library.
        setup_ssh_tunnel(local_host, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Sets up an SSH tunnel by attempting to bind to a list of local ports.
        kill_ssh_tunnel():
            Terminates the active SSH tunnel and releases the associated resources.
    Attributes:
        ssh_tunnel (SSHTunnelForwarder or None): The active SSH tunnel instance.
        binded_port (int or None): The local port successfully bound for the SSH tunnel.
        port_list (list): List of local ports to attempt binding for the SSH tunnel.
        test_info_logger (Logger): Logger instance for logging tunnel-related information.
    """
    def create_tunnel(self, local_host, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
        """
        Establishes an SSH tunnel to forward traffic from a local address to a remote address.
        Args:
            local_host (str): The local host address to bind the tunnel.
            local_port (int): The local port to bind the tunnel.
            remote_host (str): The remote host address to forward traffic to.
            remote_port (int): The remote port to forward traffic to.
            ssh_host (str): The SSH server host address.
            ssh_port (int): The SSH server port.
            ssh_username (str): The username for SSH authentication.
            ssh_password (str): The password for SSH authentication.
        Returns:
            tuple: A tuple containing:
                - bool: True if the tunnel was successfully created, False otherwise.
                - SSHTunnelForwarder or None: The SSH tunnel object if successful, None otherwise.
        Raises:
            HandlerSSHTunnelForwarderError: If the SSH tunnel cannot be created due to port conflicts.
            Exception: For any other errors encountered during tunnel creation.
        """
        
        try:
            return True, SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_username,
                    ssh_password=ssh_password,
                    remote_bind_address=(remote_host, remote_port),
                    local_bind_address=(local_host, local_port),
                    )
        except HandlerSSHTunnelForwarderError:
            self.test_info_logger.info(f"⏭️ Port {ssh_host} is already in use. Skipping..")
            return False, None
        except Exception as error:
            return False, None

    def setup_ssh_tunnel(self, local_host, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
        """
        Sets up an SSH tunnel to enable secure communication between a local and remote host.
        This method attempts to establish an SSH tunnel by iterating through a list of local ports 
        and binding to the first available port. If successful, the tunnel is started, and the 
        binded port is returned. If no port can be bound, an exception is raised.
        Args:
            local_host (str): The local host address to bind the SSH tunnel.
            local_port (list[int]): A list of local ports to attempt binding for the SSH tunnel.
            remote_host (str): The remote host address to connect to via the SSH tunnel.
            remote_port (int): The remote port to connect to on the remote host.
            ssh_host (str): The SSH server host address.
            ssh_port (int): The SSH server port.
            ssh_username (str): The username for SSH authentication.
            ssh_password (str): The password for SSH authentication.
        Raises:
            Exception: If no ports are provided in `local_port`.
            Exception: If the SSH tunnel cannot be established on any of the provided ports.
        Returns:
            int: The local port number on which the SSH tunnel is successfully established.
        
        """

        if self.ssh_tunnel:
            return

        if not local_port:
            raise Exception(f"Expecting list of ports to ssh tunnelling, found none!")
        self.port_list = local_port
        for port in self.port_list:
            status, self.ssh_tunnel = self.create_tunnel(local_host=local_host, local_port=port, remote_host=remote_host, remote_port=remote_port, 
                                             ssh_host=ssh_host, ssh_port=ssh_port,
                                            ssh_username=ssh_username, ssh_password=ssh_password)
            if status:
                self.binded_port = port
                self.ssh_tunnel.start()
                break
            self.test_info_logger.info(f"🚫 Failed to bind port {port}.")
        if self.binded_port is None:
            raise Exception(f"🚫 Failed to bind port! Please make sure the host machine has port forwarding enabled and there is at least one port available in {self.port_list}.")
        msg = f"✅ SSH tunnel established at port: {self.binded_port}"
        self.test_info_logger.info(msg)
        return self.binded_port
    
    def kill_ssh_tunnel(self):
        """
        Terminates the SSH tunnel if it is active.
        This method checks if an SSH tunnel is currently established. If so, it closes the tunnel,
        logs a success message indicating the tunnel has been terminated, and resets the `binded_port`
        attribute to `None`.
        Returns:
            None
        """
        
        if self.ssh_tunnel:
            self.ssh_tunnel.close()
            self.test_info_logger.info("🛑 SSH tunnel is killed successfully!")
            self.binded_port = None


class SSHTunnelWithSshpass(SSHTunnel):
    """
    SSHTunnelWithSshpass is a subclass of SSHTunnel that provides functionality to create, manage, 
    and terminate SSH tunnels using the `sshpass` utility. This class is particularly useful for 
    automating SSH tunneling tasks where password-based authentication is required.
    Methods:
        create_tunnel(local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Creates an SSH tunnel using the `sshpass` utility and returns the process object and any error messages.
        setup_ssh_tunnel(local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
            Sets up an SSH tunnel by attempting to bind to one of the provided local ports. Logs the status 
            and raises an exception if no port can be bound.
        kill_ssh_tunnel():
            Terminates the SSH tunnel by identifying and killing the process associated with the bound port.
    Attributes:
        ssh_tunnel (bool): Indicates whether an SSH tunnel is currently active.
        port_list (list): List of local ports to attempt binding for the SSH tunnel.
        binded_port (int): The local port successfully bound for the SSH tunnel.
        test_info_logger (Logger): Logger instance used for logging information and warnings.
    Usage:
        This class is designed to be used in scenarios where SSH tunneling is required for secure 
        communication between a local machine and a remote host. It simplifies the process of 
        setting up and tearing down SSH tunnels programmatically.
    """
    def create_tunnel(self, local_port, remote_host, remote_port, ssh_host, ssh_port, ssh_username, ssh_password):
        """
        Creates an SSH tunnel to forward a local port to a remote host and port via an SSH server.
        Args:
            local_port (int): The local port to bind for the tunnel.
            remote_host (str): The remote host to forward the connection to.
            remote_port (int): The remote port to forward the connection to.
            ssh_host (str): The SSH server host to connect through.
            ssh_port (int): The port of the SSH server.
            ssh_username (str): The username for SSH authentication.
            ssh_password (str): The password for SSH authentication.
        Returns:
            tuple: A tuple containing:
                - process (subprocess.Popen): The subprocess running the SSH command.
                - stderr_data (str): The standard error output from the SSH command.
        Note:
            This method uses `sshpass` to handle password-based SSH authentication.
            Ensure `sshpass` is installed and available in the system's PATH.
            The `StrictHostKeyChecking` option is disabled for convenience, which may pose a security risk.
        """
        
        ssh_cmd = "sshpass -p {ssh_password} ssh -4 -o StrictHostKeyChecking=no -fNT -L\
                {binded_port}:{amc_ip}:{remote_port} {ssh_username}@{bmc_ip} -p {ssh_port}".format(
                    ssh_password = ssh_password,
                    binded_port = local_port,
                    ssh_username = ssh_username,
                    bmc_ip = ssh_host,
                    amc_ip = remote_host,
                    ssh_port=ssh_port,
                    remote_port=remote_port
                    )
        process = subprocess.Popen(ssh_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout_data, stderr_data = process.communicate()
        return process, stderr_data

    def setup_ssh_tunnel(self, local_port, remote_host, remote_port, ssh_host,
            ssh_port, ssh_username, ssh_password):
        """
        Sets up an SSH tunnel by attempting to bind to one of the provided local ports.
        This method establishes an SSH tunnel between a local port and a remote host/port
        using the provided SSH credentials. It iterates through the list of local ports
        and attempts to bind to each one until a successful connection is established.
        Args:
            local_port (list[int]): A list of local ports to attempt binding for the SSH tunnel.
            remote_host (str): The hostname or IP address of the remote host to connect to.
            remote_port (int): The port on the remote host to forward traffic to.
            ssh_host (str): The hostname or IP address of the SSH server.
            ssh_port (int): The port of the SSH server (default is typically 22).
            ssh_username (str): The username for SSH authentication.
            ssh_password (str): The password for SSH authentication.
        Returns:
            int: The local port that was successfully bound for the SSH tunnel.
        Raises:
            Exception: If no local port could be bound or if the provided list of ports is empty.
        Notes:
            - If an SSH tunnel is already established (`self.ssh_tunnel` is True), the method
                returns immediately without creating a new tunnel.
            - Logs information about the success or failure of binding to each port.
            - Ensures that at least one port from the provided list is successfully bound,
                otherwise raises an exception.
        """

        if self.ssh_tunnel:
            return

        if not local_port:
            raise Exception(f"Expecting list of ports to ssh tunnelling, found none!")
        self.port_list = local_port
        for port in self.port_list:
            process, stderr_data = self.create_tunnel(local_port=port, remote_host=remote_host, remote_port=remote_port,
                                             ssh_host=ssh_host, ssh_port=ssh_port,
                                            ssh_username=ssh_username, ssh_password=ssh_password)
            if process.returncode != 0 or stderr_data:
                msg = f"⏭️ Failed to bind port {port}.\nReturnCode: {process.returncode}\nError: {stderr_data}\nTrying the next one..."
                self.test_info_logger.info(msg)
            else:
                self.binded_port = port
                self.ssh_tunnel = True
                break
        if self.binded_port is None:
            raise Exception(f"❌ Failed to bind port! Please make sure the host machine has port forwarding enabled and there is at least one port available in {local_port}.")
        msg = f"✅ SSH tunnel established at port: {self.binded_port}"
        self.test_info_logger.info(msg)
        return self.binded_port

    def kill_ssh_tunnel(self):
        """
        Terminates the SSH tunnel by killing the processes associated with the binded port.
        This method identifies all the process IDs (PIDs) associated with the binded port
        and terminates them, ensuring that the current process is not killed in the process.
        Steps:
        1. Uses the `lsof` command to find all PIDs associated with the binded port.
        2. Iterates through the list of PIDs and skips the current process's PID.
        3. Executes the `kill` command to terminate the identified processes.
        4. Logs a warning if the process termination fails, or logs success if the tunnel is killed.
        Attributes:
            binded_port (int): The port number currently bound to the SSH tunnel.
            test_info_logger (Logger): Logger instance used for logging messages.
        Notes:
            - This method uses subprocess to execute shell commands (`lsof` and `kill`).
            - The `binded_port` attribute is set to `None` after successful termination
              to ensure thread safety in multi-threaded environments.
        Raises:
            None: Any errors during the process termination are logged but not raised.
        """
        
        
        # First, find all the PIDs associated with the binded port
        port_pid = ["lsof", "-t", "-i", ":{0}".format(self.binded_port)] # ANother option is to add -sTCP:LISTEN
        process = subprocess.Popen(port_pid, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        my_pid = os.getpid()
        for this_pid in list(filter(None, stdout.decode().strip().split('\n'))):
            # Make sure to not kill this running process
            if int(this_pid) != my_pid:
                kill_cmd = "kill {}".format(this_pid)
                process = subprocess.Popen(kill_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdout_data, stderr_data = process.communicate()
                if process.returncode != 0 or stderr_data:
                    msg = f"⚠️ WARNING: Couldn't close the port forwarding! {kill_cmd}\nReturnCode: {process.returncode}\nError: {stderr_data}"
                    self.test_info_logger.info(msg)
                else:
                    self.test_info_logger.info("🔌 SSH tunnel is killed successfully!")
                    self.binded_port = None # Just for sanity in case of multi-threading