import asyncio
from datetime import datetime
import importlib
import inspect
import os
import pytz
import traceback
from typing import Dict, Optional
import yaml
from node.utils import get_logger
from node.celery_worker.utils import (
    BASE_OUTPUT_DIR,
    MODULES_PATH,
    handle_ipfs_input,
    update_db_with_status_sync,
    upload_to_ipfs,
)
from node.nodes import Node
from node.schemas import Job


logger = get_logger(__name__)


def load_yaml_config(cfg_path):
    with open(cfg_path, "r") as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def dynamic_import_and_run(validated_data, nodes, job, cfg):
    tn = job["module_id"].replace("-", "_")
    entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]
    main_module = importlib.import_module(f"{tn}.run")
    main_func = getattr(main_module, entrypoint)

    if inspect.iscoroutinefunction(main_func):
        return asyncio.run(main_func(validated_data, nodes, job, cfg=cfg))
    else:
        return main_func(validated_data, nodes, job, cfg=cfg)


def load_and_validate_input_schema(template_name, template_args):
    tn = template_name.replace("-", "_")
    schemas_module = importlib.import_module(f"{tn}.schemas")
    InputSchema = getattr(schemas_module, "InputSchema")
    return InputSchema(**template_args)


def prepare_input_dir(template_args: Dict, input_dir: Optional[str] = None, input_ipfs_hash: Optional[str] = None):
    """Prepare the input directory"""
    # make sure only input_dir or input_ipfs_hash is present
    if input_dir and input_ipfs_hash:
        raise ValueError("Only one of input_dir or input_ipfs_hash can be provided")

    if input_dir:
        input_dir = f"{BASE_OUTPUT_DIR}/{input_dir}"
        template_args["input_dir"] = input_dir

        if not os.path.exists(input_dir):
            raise ValueError(f"Input directory {input_dir} does not exist")

    if input_ipfs_hash:
        input_dir = handle_ipfs_input(input_ipfs_hash)
        template_args["input_dir"] = input_dir

    return template_args


def run_template_job(job: Job):
    """Run a template job"""
    try:
        logger.info(f"Running template job: {job}")
        job["status"] = "running"
        asyncio.run(update_db_with_status_sync(job_data=job))

        if hasattr(job, 'coworkers') and job['coworkers'] is not None:
            nodes = [Node(coworker) for coworker in job['coworkers']]
        else:
            nodes = None

        template_name = job["module_id"]
        template_args = job["module_params"]
        template_path = f"{MODULES_PATH}/{template_name}"
        cfg = load_yaml_config(f"{template_path}/{template_name}/component.yaml")

        # prepare input_dir if have to
        if "input_dir" in template_args or "input_ipfs_hash" in template_args:
            template_args = prepare_input_dir(
                template_args=template_args,
                input_dir=template_args.get("input_dir", None),
                input_ipfs_hash=template_args.get("input_ipfs_hash", None)
            )

        if cfg["outputs"]["save"]:
            output_path = f"{BASE_OUTPUT_DIR}/{job['id'].split(':')[1]}"
            template_args["output_path"] = output_path
            if not os.path.exists(output_path):
                os.makedirs(output_path)

        validated_data = load_and_validate_input_schema(template_name, template_args)
        results = dynamic_import_and_run(validated_data, nodes, job, cfg)

        save_location = template_args.get("save_location", None)
        if save_location: # save_location is a new key in the template_args; ipfs or node
            cfg["outputs"]["location"] = save_location

        if cfg["outputs"]["save"]:
            if cfg["outputs"]["location"] == "node":
                out_msg = {
                    "output": results
                }
            elif cfg["outputs"]["location"] == "ipfs":
                out_msg = upload_to_ipfs(template_args["output_path"])
                out_msg = f"IPFS Hash: {out_msg}"
                out_msg = {
                    "output": out_msg
                }
            else:
                raise ValueError(f"Invalid location: {cfg['outputs']['location']}")
        else:
            out_msg = {
                "output": results
            }

        job["status"] = "completed"
        job["reply"] = out_msg
        job["error"] = False
        job["error_message"] = ""
        job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        asyncio.run(update_db_with_status_sync(job_data=job))

        logger.info(f"Template job completed: {job}")

    except Exception as e:
        logger.error(f"Error running template job: {e}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        job["status"] = "error"
        job["error"] = True
        job["error_message"] = str(e) + error_details
        job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        asyncio.run(update_db_with_status_sync(job_data=job))
