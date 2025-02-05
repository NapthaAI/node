#!/usr/bin/env python3
from dotenv import load_dotenv
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional
import yaml
from node.config import LLM_BACKEND, OLLAMA_MODELS, OPENAI_MODELS, VLLM_MODELS, LAUNCH_DOCKER, MODEL_SERVICE_MAP

load_dotenv()

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
            service_name = MODEL_SERVICE_MAP.get(model)
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

def main():
    # Generate config
    config = generate_litellm_config()
    
    if not config['model_list']:
        print("Error: No models configured. Please check OPENAI_MODELS and OLLAMA_MODELS in your configuration.")
        sys.exit(1)
    
    # Determine the output path - this should be in the litellm directory
    script_dir = Path(__file__).parent
    output_path = script_dir / 'litellm_config.yml'
    
    # Write the configuration
    try:
        with open(output_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"Successfully generated LiteLLM config at {output_path}")
    except Exception as e:
        print(f"Error writing config file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()