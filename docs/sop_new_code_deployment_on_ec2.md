# Standard Operating Procedure: New Code Deployment on EC2

This document outlines the standard, step-by-step procedure for safely deploying new code updates to the live production environment on the AWS EC2 instance. Following these steps ensures that the running application is always using the latest, correct version of the code and its dependencies.

## Deployment Workflow

After committing and pushing changes from your local machine, follow these steps on the EC2 instance to deploy the update:

1.  **Connect and Navigate**: SSH into the server and `cd` to the project directory.

2.  **Stop the Old Process**: Stop the currently running live engine using its Process ID (PID) stored in the `pid_file`.
    ```bash
    kill $(cat data/live_engine.pid)
    sleep 5 # Wait a few seconds for graceful shutdown
    ```

3.  **Update Code**: Force sync the local repository with the remote `main` branch to pull the latest changes.
    ```bash
    git fetch origin
    git reset --hard origin/main
    ```

4.  **Sync Environment**: Activate the virtual environment (`poetry shell`) and install any new or updated dependencies. This is a safe and idempotent command.
    ```bash
    poetry install
    ```

5.  **Start the New Process**: Start the live trading engine again using `nohup`. The new process will now use the updated code.
    ```bash
    nohup python src/tick_collector.py &
    ```