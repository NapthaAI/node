# Node Test Scripts

This directory contains test scripts for the Node server, covering HTTP, WebSocket, and gRPC interfaces.

## Test Scripts Overview

1. **HTTP Direct Tests (`http_direct.py`):**
   - Check user
   - Register user
   - Run single agent
   - Run multi-agent
   - Read/write storage
   - Read/write IPFS

2. **WebSocket Direct Tests (`ws_direct.py`):**
   - Check user
   - Register user
   - Run single agent
   - Run multi-agent
   - Read/write storage
   - Read/write IPFS

3. **gRPC Direct Tests (`grpc_direct.py`):**
   - Check user
   - Register user
   - Run single agent
   - Run multi-agent

## Prerequisites
- Install required dependencies:
```
pip install httpx websockets grpcio grpcio-tools
```

## Running the Tests

1. **Configure the server:**
 - Open `config.py` in the root directory
 - Adjust the settings according to your test environment (e.g., server addresses, ports)

2. **Start the server:**
 - Run the `launch.sh` script to start the Node server

```bash
 ./launch.sh
```
3. **Navigate to the tests directory:**
```bash
cd ./tests
```
4. **Run the test scripts:**

- For HTTP tests:
  ```
  python http_direct.py
  ```

- For WebSocket tests:
  ```
  python ws_direct.py
  ```

- For gRPC tests:
  ```
  python grpc_direct.py
  ```

## Test Output

- Each test script will output detailed logs of the test execution.
- Successful tests will pass without errors.
- Failed tests will raise assertions with details about the failure.

## Troubleshooting

- If tests fail, check the server logs for any backend errors.
- Ensure that the server is running and accessible at the configured address.
- Verify that all required services (e.g., IPFS, database) are operational.

## Adding New Tests

To add new tests:
1. Open the relevant test script (`http_direct.py`, `ws_direct.py`, or `grpc_direct.py`).
2. Add a new test method to the `TestHTTPServer`, `TestWSServer`, or `TestGRPCServer` class.
3. Implement the test logic using the appropriate client (HTTP, WebSocket, or gRPC).

## Note

These tests are designed to run against a live server. Ensure that your test environment is properly isolated to prevent interference with production data.