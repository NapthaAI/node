### Build image
```bash
docker build -t phi2 .
```

### Docker Inference
```bash
docker run -v /Users/arshath/play/daimon/test-dockers/phi2:/app/output \
    --rm phi2 python inference.py \
    --system_prompt "You are math genius" \
    --user_prompt "Write a math joke" \
    --output_dir /app/output
```