#!/usr/bin/env python3
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.append(str(root_dir))
from node.config import LLM_BACKEND, OLLAMA_MODELS, OPENAI_MODELS, VLLM_MODELS, LAUNCH_DOCKER, MODEL_SERVICE_MAP

def format_yaml_value(value: any) -> str:
    """Format a value for YAML output."""
    if isinstance(value, str):
        if any(c in value for c in ":{}\n[]'\""):
            return "'{}'".format(value.replace("'", "''"))
        return value
    if isinstance(value, (bool, int, float)):
        return str(value).lower()
    return str(value)

def dict_to_yaml(data: Dict, indent: int = 0) -> str:
    """Convert a dictionary to YAML string."""
    yaml_str = []
    spaces = " " * indent
    
    for key, value in data.items():
        if isinstance(value, dict):
            yaml_str.append(f"{spaces}{key}:")
            yaml_str.append(dict_to_yaml(value, indent + 2))
        elif isinstance(value, list):
            yaml_str.append(f"{spaces}{key}:")
            for item in value:
                if isinstance(item, dict):
                    # Start dictionary items in a list with "- key:" format
                    first_key = next(iter(item))
                    yaml_str.append(f"{spaces}- {first_key}: {format_yaml_value(item[first_key])}")
                    # Handle remaining key-value pairs with increased indentation
                    remaining = {k: v for k, v in item.items() if k != first_key}
                    if remaining:
                        yaml_str.append(dict_to_yaml(remaining, indent + 2))
                else:
                    yaml_str.append(f"{spaces}- {format_yaml_value(item)}")
        else:
            yaml_str.append(f"{spaces}{key}: {format_yaml_value(value)}")
    
    return "\n".join(yaml_str)

def validate_openai_key() -> Optional[str]:
    """Validate OpenAI API key from environment."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("No OPENAI_API_KEY found in environment")
        return None
    
    if len(api_key) < 10:
        print("OPENAI_API_KEY seems invalid (length < 10)")
        return None
        
    return api_key

def get_openai_models() -> List[str]:
    """Get OpenAI models from config."""
    if not OPENAI_MODELS:
        return []
    return [model.strip() for model in OPENAI_MODELS.split(',') if model.strip()]

def get_ollama_models() -> List[str]:
    """Get Ollama models from config."""
    if not OLLAMA_MODELS:
        return []
     # NOTE requires that we
    return [model.strip() for model in OLLAMA_MODELS.split(',') if model.strip()]

def get_vllm_models() -> List[str]:
    """Get VLLM models from config."""
    if not VLLM_MODELS:
        return []
    return VLLM_MODELS

def generate_litellm_config() -> Dict:
    """Generate LiteLLM configuration."""
    config = {
        'model_list': []
    }
    
    # Add OpenAI models if API key is valid
    if validate_openai_key():
        openai_models = get_openai_models()
        for model in openai_models:
            config['model_list'].append({
                'model_name': model,
                'litellm_params': {
                    'model': f'openai/{model}',
                    'api_key': 'os.environ/OPENAI_API_KEY'
                }
            })
    
    # Add models based on LLM_BACKEND
    if LLM_BACKEND == "ollama":
        ollama_models = get_ollama_models()
        for model in ollama_models:
            config['model_list'].append({
                'model_name': model,
                'litellm_params': {
                    'model': f'ollama/{model}',
                    'api_base': 'http://localhost:11434' if not LAUNCH_DOCKER else 'http://ollama:11434'
                }
            })

    elif LLM_BACKEND == "vllm":
        vllm_models = get_vllm_models()
        for model in vllm_models:
            service_name = model.split("/")[-1]
            if service_name:
                if "embeddings" not in service_name:
                    config['model_list'].append({
                        'model_name': model,
                        'litellm_params': {
                            'model': f'openai/{model}',
                            'api_base': f'http://{service_name}:8000/v1',
                            'api_key': 'none'
                        }
                    })
                else:
                    config['model_list'].append({
                        'model_name': model,
                        'litellm_params': {
                            'model': f'openai/{model}',
                            'api_base': f'http://{service_name}/v1',
                            'api_key': 'none'
                        }
                    })
            else:
                print(f"Model {model} not found in MODEL_SERVICE_MAP")

    # add api key at the bottom of the config
    config['general_settings'] = {
        'master_key': os.getenv('LITELLM_MASTER_KEY')
    }
    
    return config

def get_gpu_var_name(model_name: str) -> str:
    """Generate standardized GPU ID variable name from model name."""
    # Get the part after the last slash
    base_name = model_name.split('/')[-1]
    # Convert to lowercase and replace special chars with underscores
    normalized = base_name.lower().replace('-', '_').replace('.', '_')
    return f"GPU_ID_{normalized}"

def allocate_gpus(model_map, vllm_models):
    """
    Allocate GPUs based on model requirements.
    Returns a space-separated string of GPU assignments for docker compose.
    """
    current_gpu = 0
    gpu_assignments = []

    for model in vllm_models:
        if model not in model_map:
            print(f"Warning: {model} not found in MODEL_SERVICE_MAP", file=sys.stderr)
            continue

        gpu_count = model_map[model]  # Now directly get the GPU count
        gpu_var_name = get_gpu_var_name(model)
        
        # Check if we have enough GPUs
        if current_gpu + gpu_count > 8:  # Assuming 8 GPUs
            print(f"Error: Not enough GPUs for {model}", file=sys.stderr)
            sys.exit(1)
        
        # Create GPU list for this model
        gpu_list = ",".join(str(i) for i in range(current_gpu, current_gpu + gpu_count))
        gpu_assignments.append(f"{gpu_var_name}={gpu_list}")
        current_gpu += gpu_count

    return " ".join(gpu_assignments)

def main():
    # Generate config
    config = generate_litellm_config()
    
    if not config['model_list']:
        print("Error: No models configured. Please check OPENAI_MODELS and OLLAMA_MODELS in your configuration.", file=sys.stderr)
        sys.exit(1)
    
    # Determine the output path - this should be in the litellm directory
    script_dir = Path(__file__).parent
    output_path = script_dir / 'litellm_config.yml'
    
    # Write the configuration
    try:
        yaml_content = dict_to_yaml(config)
        with open(output_path, 'w') as f:
            f.write(yaml_content)
        print(f"Successfully generated LiteLLM config at {output_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing config file: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate GPU assignments
    if LLM_BACKEND == "vllm":
        gpu_assignments = allocate_gpus(MODEL_SERVICE_MAP, VLLM_MODELS)
        print(gpu_assignments)  # This will go to stdout

if __name__ == "__main__":
    main()