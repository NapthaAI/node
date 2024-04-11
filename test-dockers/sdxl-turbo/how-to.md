### Build image
```bash
docker build -t sdxl-turbo .
```

### Docker Inference
```bash
docker run -v /Users/arshath/play/daimon/test-dockers/sdxl-turbo:/app/output \
    --rm sdxl-turbo python -m inference.py \
    --prompt "Indian monk in an icy mountain" \
    --output_dir /app/output
```