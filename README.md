Download the models from [this link](https://uts.nlm.nih.gov/uts/login?service=https://medcat.rosalind.kcl.ac.uk/auth-callback)

## Installation & Usage

#### Install
pip install requests medcat colorama flask flask_cors pandas celera redis pydantic openai

#### Environment Variables
export OPENAI_API_KEY='sk-proj-*-*-*--*'

#### Run API
python app.py

#### Run Worker
celery -A app.celery worker --loglevel=info --pool=solo

## Deployment

### Create SSH Alias configuration & Connect

1. Open the SSH Config File

    ```bash
    nano ~/.ssh/config
    ```

    If the file does not exist, create it.

2. Add the SSH Alias Configuration

    ```bash
    Host itri_dhp
        HostName 35.95.243.198
        User ubuntu
        Port 22
        IdentityFile ~/.ssh/itri_dechnology_developer.pem
    ```

    - Host → The alias you want to use for the SSH connection.
    - HostName → The actual IP address or domain of the remote server.
    - User → The username to log in.
    - Port → The port number (default SSH port is 22).
    - IdentityFile → The SSH private key file to use for authentication (in AWS folder).

3. Save and Exit

    - Press CTRL + X, then Y, and press Enter to save the changes.

4. Connect Using the Alias Instead of typing a full command like:

    ```bash
    ssh ubuntu@35.95.243.198 -p 22
    ```

    You can now simply run:

    ```bash
    ssh itri_dhp
    ```

### Upload the Project via sFTP (e.g., FileZilla)

To upload the project files to the remote server using sFTP, follow these steps:

#### Prerequisites
Ensure you have the following:
- FileZilla (or any sFTP client of your choice) installed.
- The necessary SSH private key (`~/.ssh/itri_dechnology_developer.pem`).
- The following server credentials:
  ```
  Host: itri_dhp
  HostName: 35.95.243.198
  User: ubuntu
  Port: 22
  IdentityFile: ~/.ssh/itri_dechnology_developer.pem
  ```

#### Steps to Upload the Project

1. **Open FileZilla**
   - If you haven't installed FileZilla, download it from [FileZilla Official Site](https://filezilla-project.org/).

2. **Open the Site Manager**
   - Click on `File` → `Site Manager` (or press `Ctrl + S`).

3. **Add a New Site**
   - Click `New Site` and name it `itri_dhp`.
   - In the `General` tab, configure the following:
     - **Protocol**: SFTP – SSH File Transfer Protocol
     - **Host**: `35.95.243.198`
     - **Port**: `22`
     - **Logon Type**: Key file
     - **User**: `ubuntu`
     - **Key file**: Select `~/.ssh/itri_dechnology_developer.pem`

4. **Connect to the Server**
   - Click `Connect` to establish the connection.
   - If prompted about the server's host key, accept and proceed.

5. **Upload the Project Files**
   - In the local panel (left side), navigate to your project directory.
   - In the remote panel (right side), navigate to the target directory.
   - Drag and drop files from your local directory to the remote directory (~/project).

6. **Verify the Upload**
   - Check the `Successful Transfers` tab to ensure all files have been uploaded correctly.
   - If any errors occur, refer to the `Failed Transfers` tab and retry the upload.

#### Additional Notes
- If you encounter connection issues, ensure your private key permissions are correctly set:  
  ```sh
  chmod 600 ~/.ssh/itri_dechnology_developer.pem
  ```

This guide should help you smoothly upload your project via sFTP. 🚀


### Running `app.py` Using `screen`

To execute `app.py` in an existing or new `screen` session, follow these steps.

#### Prerequisites

Ensure you have access to the server and can use `screen`:

- SSH into the server.
- Verify if there are existing `screen` sessions using:
  ```sh
  screen -ls
  ```
  Example output:
  ```sh
  There are screens on:
      132573.fhir_tool_worker (Detached)
      84841.fhir_tools_ner    (Detached)
  ```
  The two relevant sessions are:
  - `132573.fhir_tool_worker` (API Service)
  - `84841.fhir_tools_ner` (Job Worker)

#### Reattach to an Existing `screen` Session

1. **Reconnect to an Existing Session**

   ```sh
   screen -r 84841
   ```

   Replace `84841` with the actual session ID from the `screen -ls` output.

2. **Check if the Application is Running**

   - If `app.py` is running, you can monitor its output.
   - If `app.py` is not running, restart it using:
     ```sh
     cd ~/project/src
     python app.py
     ```

3. **Detach from the Session Without Stopping the Process**

   - Press `Ctrl + A`, then `D` to detach and keep it running in the background.

#### Running the Celery Worker

To start the Celery worker for job processing, follow these steps:

1. **Reattach to the Worker Screen Session**
   ```sh
   screen -r 132573
   ```
   Replace `132573` with the actual session ID for the worker.

2. **Check if the Worker is Running**
   - If the worker is not running, restart it using:
     ```sh
     cd ~/project/src
     celery -A app.celery worker --loglevel=info --pool=solo
     ```

3. **Detach from the Worker Session**
   - Press `Ctrl + A`, then `D` to keep it running in the background.

#### Create a New `screen` Session (If Needed)

If no existing session is available or you accidentally closed it, you can create a new one:

1. **Start a New `screen` Session**

   ```sh
   screen -S app_session
   ```

   This creates a new `screen` session named `app_session`.

2. **Navigate to the Project Directory**

   ```sh
   cd ~/project/src
   ```

3. **Activate the Conda Environment**

   ```sh
   conda activate snomed2
   ```

4. **Run `app.py`**

   ```sh
   python app.py
   ```

5. **Start the Celery Worker**

   ```sh
   screen -S worker_session
   ```
   ```sh
   cd ~/project/src
   celery -A app.celery worker --loglevel=info --pool=solo
   ```

6. **Detach from the Sessions**
   - Press `Ctrl + A`, then `D` to detach both `app_session` and `worker_session`.
   - Verify that the sessions are still active:
     ```sh
     screen -ls
     ```

7. **Terminate the Sessions** (if no longer needed)

   - Reattach using `screen -r app_session` or `screen -r worker_session`
   - Stop the running process with `Ctrl + C`
   - Exit the session:
     ```sh
     exit
     ```
   - Verify that the session is removed using `screen -ls`.

#### Additional Notes

- If `screen` is not installed, you can install it using:
  ```sh
  sudo apt install screen
  ```
- The `conda activate snomed2` step is only required when creating a new session, as the currently running sessions are already using the `snomed2` environment.

By following these steps, `app.py` and the Celery worker will continue running even after logging out from the server. 🚀


