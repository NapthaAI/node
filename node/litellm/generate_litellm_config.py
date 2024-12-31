#!/usr/bin/env python3
import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import sys
from node.config import OLLAMA_MODELS, OPENAI_MODELS

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
    return [model.strip() for model in OLLAMA_MODELS.split(',') if model.strip()]

def generate_litellm_config() -> Dict:
    """Generate LiteLLM configuration."""
    config = {
        'model_list': [],
        'litellm_settings': {
            'enable_json_schema_validation': True
        }
    }
    
    # Add OpenAI models if API key is valid
    if validate_openai_key():
        openai_models = get_openai_models()
        for model in openai_models:
            config['model_list'].append({
                'model_name': 'openai:' + model,
                'litellm_params': {
                    'model': f'openai/{model}',
                    'api_key': 'os.environ/OPENAI_API_KEY'
                }
            })
    
    # Add Ollama models
    ollama_models = get_ollama_models()
    for model in ollama_models:
        config['model_list'].append({
            'model_name': model,
            'litellm_params': {
                'model': f'ollama/{model}',
                'api_base': 'http://localhost:11434'
            }
        })
    
    return config

def main():
    # Generate config
    config = generate_litellm_config()
    
    if not config['model_list']:
        print("Error: No models configured. Please check OPENAI_MODELS and OLLAMA_MODELS in your configuration.")
        sys.exit(1)
    
    # Determine the output path - this should be in the litellm directory
    script_dir = Path(__file__).parent
    output_path = script_dir / 'litellm_config.yaml'
    
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