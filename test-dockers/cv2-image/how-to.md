### Build image
```bash
docker build -t cv2-image .
```

### Docker Inference
```bash
docker run -v /Users/arshath/play/daimon/test-dockers/cv2-image:/app/output \
    --rm cv2-image python -m inference \
    --prompt "Algovera" \
    --output_dir /app/output
```