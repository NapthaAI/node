CREATE invite SET code="DZHA4ZTK";

CREATE license:apache2 SET license_type="Apache 2.0", details="https://www.apache.org/licenses/LICENSE-2.0";
CREATE license:mit SET license_type="MIT", details="https://opensource.org/licenses/MIT";

CREATE category:multimodal SET name="Multimodal";
-- subcategories for multimodal
CREATE category:feature_extraction SET name="Feature Extraction", parent_categories=[category:multimodal];
CREATE category:text_to_image SET name="Text-to-Image", parent_categories=[category:multimodal];
CREATE category:image_to_text SET name="Image-to-Text", parent_categories=[category:multimodal];
CREATE category:image_to_video SET name="Image-to-Video", parent_categories=[category:multimodal];
CREATE category:text_to_video SET name="Text-to-Video", parent_categories=[category:multimodal];
CREATE category:visual_question_answering SET name="Visual Question Answering", parent_categories=[category:multimodal];
CREATE category:document_question_answering SET name="Document Question Answering", parent_categories=[category:multimodal];
CREATE category:graph_machine_learning SET name="Graph Machine Learning", parent_categories=[category:multimodal];
CREATE category:text_to_3d SET name="Text-to-3D", parent_categories=[category:multimodal];
CREATE category:image_to_3d SET name="Image-to-3D", parent_categories=[category:multimodal];

CREATE category:computer_vision SET name="Computer Vision";
-- subcategories for computer vision
CREATE category:depth_estimation SET name="Depth Estimation", parent_categories=[category:computer_vision];
CREATE category:image_classification SET name="Image Classification", parent_categories=[category:computer_vision];
CREATE category:object_detection SET name="Object Detection", parent_categories=[category:computer_vision];
CREATE category:image_segmentation SET name="Image Segmentation", parent_categories=[category:computer_vision];
CREATE category:image_to_image SET name="Image-to-Image", parent_categories=[category:computer_vision];
CREATE category:unconditional_image_generation SET name="Unconditional Image Generation", parent_categories=[category:computer_vision];
CREATE category:video_classification SET name="Video Classification", parent_categories=[category:computer_vision];
CREATE category:zero_shot_image_classification SET name="Zero-Shot Image Classification", parent_categories=[category:computer_vision];
CREATE category:mask_generation SET name="Mask Generation", parent_categories=[category:computer_vision];
CREATE category:zero_shot_object_detection SET name="Zero-Shot Object Detection", parent_categories=[category:computer_vision];

CREATE category:natural_language_processing SET name="Natural Language Processing";
-- subcategories for natural language processing
CREATE category:text_classification SET name="Text Classification", parent_categories=[category:natural_language_processing];
CREATE category:token_classification SET name="Token Classification", parent_categories=[category:natural_language_processing];
CREATE category:table_question_answering SET name="Table Question Answering", parent_categories=[category:natural_language_processing];
CREATE category:question_answering SET name="Question Answering", parent_categories=[category:natural_language_processing];
CREATE category:zero_shot_classification SET name="Zero-Shot Classification", parent_categories=[category:natural_language_processing];
CREATE category:translation SET name="Translation", parent_categories=[category:natural_language_processing];
CREATE category:summarization SET name="Summarization", parent_categories=[category:natural_language_processing];
CREATE category:conversational SET name="Conversational", parent_categories=[category:natural_language_processing];
CREATE category:text_generation SET name="Text Generation", parent_categories=[category:natural_language_processing];
CREATE category:text2text_generation SET name="Text2Text Generation", parent_categories=[category:natural_language_processing];
CREATE category:fill_mask SET name="Fill-Mask", parent_categories=[category:natural_language_processing];
CREATE category:sentence_similarity SET name="Sentence Similarity", parent_categories=[category:natural_language_processing];

CREATE category:audio SET name="Audio";
-- subcategories for Audio
CREATE category:text_to_speech SET name="Text-to-Speech", parent_categories=[category:audio];
CREATE category:text_to_audio SET name="Text-to-Audio", parent_categories=[category:audio];
CREATE category:automatic_speech_recognition SET name="Automatic Speech Recognition", parent_categories=[category:audio];
CREATE category:audio_to_audio SET name="Audio-to-Audio", parent_categories=[category:audio];
CREATE category:audio_classification SET name="Audio Classification", parent_categories=[category:audio];
CREATE category:voice_activity_detection SET name="Voice Activity Detection", parent_categories=[category:audio];
CREATE category:tabular SET name="Tabular", parent_categories=[category:audio];
CREATE category:tabular_classification SET name="Tabular Classification", parent_categories=[category:audio];
CREATE category:tabular_regression SET name="Tabular Regression", parent_categories=[category:audio];

CREATE category:reinforcement_learning SET name="Reinforcement Learning";
-- subcategories for Reinforcement Learning
CREATE category:reinforcement_learning SET name="Reinforcement Learning", parent_categories=[category:reinforcement_learning];
CREATE category:robotics SET name="Robotics", parent_categories=[category:reinforcement_learning];

CREATE category:simulation SET name="Simulation";
-- subcategories for Simulation
CREATE category:human_behavior SET name="Simulate Human Behavior", parent_categories=[category:simulation];
CREATE category:economic_behavior SET name="Simulate Economic Behavior", parent_categories=[category:simulation];
CREATE category:market_research SET name="Simulate Market Research", parent_categories=[category:simulation];
CREATE category:social_enagement SET name="Simulate Social Engagement", parent_categories=[category:simulation];
CREATE category:public_opinion SET name="Simulate Public Opinion", parent_categories=[category:simulation];
CREATE category:geopolitics SET name="Simulate Geopolitics", parent_categories=[category:simulation];

CREATE tag:math SET name="Math";
CREATE tag:education SET name="Education";
CREATE tag:language SET name="Language";
CREATE tag:general SET name="General";
CREATE tag:task_identification SET name="Task Identification";
CREATE tag:parallel_execution SET name="Parallel Execution";
CREATE tag:task_coordination SET name="Task Coordination";
CREATE tag:result_synthesis SET name="Result Synthesis";
CREATE tag:retrieval_augmented_generation SET name="Retrieval Augmented Generation";
CREATE tag:schema_based_tabular_data SET name="Schema-Based Tabular Data";

-- USERS
CREATE user:naptha SET 
    name="Naptha", 
    username="naptha1", 
    password=crypto::argon2::generate("great-password"),
    public_key="d3f40913bf024fbc0e7e17c298b5fa03c3518039bf71c170faf74c0694caad60503146befe78e62794c33bf7fe991175da838609c70d79d5e85bb9b1aa965a11"

;
--private_key="60a632f3e0875111199c4323a1b010bc4808e2a252b21ff366968cfc25af6444"

-- ORGANIZATIONS
CREATE organization:naptha SET name="Naptha", image="https://richardblythman.github.io/image-api/algovera/algovera-whiteBackground.png?w=200&amp;h=200&amp;f=face", owner=user:naptha1;
RELATE user:seller1->is_associated_with->organization:naptha;


-- AGENTS
CREATE agent:hello_world_agent SET name="hello_world_agent", description="A simple hello world agent", author=user:naptha, url="https://github.com/NapthaAI/hello_world_agent", type="package", version="0.13", entrypoint="run.py";
CREATE agent:simple_chat_agent SET name="simple_chat_agent", description="A simple chat agent", author=user:naptha, url="https://github.com/NapthaAI/simple_chat_agent", type="package", version="0.12", entrypoint="run.py";
CREATE agent:generate_image SET name="generate_image", description="A simple agent for generating an image from text with Stable Diffusion", author=user:naptha, url="https://github.com/NapthaAI/module_generate_image", type="package", version="0.9", entrypoint="run.py";
CREATE agent:image_to_image SET name="image_to_image", description="A simple agent for generating an image from another image with Stable Diffusion", author=user:naptha, url="https://github.com/NapthaAI/module_image2image", type="package", version="0.8", entrypoint="run.py";
CREATE agent:babyagi_task_initiator SET name="babyagi_task_initiator", description="A simple agent for initiating tasks in BabyAGI", author=user:naptha, url="https://github.com/NapthaAI/babyagi_task_initiator", type="package", version="0.2", entrypoint="run.py";
CREATE agent:babyagi_task_executor SET name="babyagi_task_executor", description="A simple agent for executing tasks in BabyAGI", author=user:naptha, url="https://github.com/NapthaAI/babyagi_task_executor", type="package", version="0.2", entrypoint="run.py";
CREATE agent:babyagi_task_finalizer SET name="babyagi_task_finalizer", description="A simple agent for finalizing tasks in BabyAGI", author=user:naptha, url="https://github.com/NapthaAI/babyagi_task_finalizer", type="package", version="0.2", entrypoint="run.py";
CREATE agent:prediction_agent SET name="prediction_agent", description="A simple agent for making predictions about events", author=user:naptha, url="https://github.com/NapthaAI/prediction_agent", type="package", version="0.3", entrypoint="run.py";
CREATE agent:debate_agent SET name="debate_agent", description="An agent for taking part in debate protocols", author=user:naptha, url="https://github.com/NapthaAI/debate_agent", type="package", version="0.2", entrypoint="run.py";
CREATE agent:napthaville_module SET name="napthaville_module", description="An agent for taking part in socail simulations", author=user:naptha, url="https://github.com/moarshy/napthaville_module", type="package", version="0.36", entrypoint="run.py";
CREATE agent:docker_hello_world SET name="docker_hello_world", description="A simple hello world app using docker", author=user:naptha, url="https://hub.docker.com/_/hello-world", type="docker", version="0.1", entrypoint="run.py";
CREATE agent:module_test SET name="module_test", description="A simple test agent", author=user:naptha, url="https://github.com/moarshy/module_test", type="package", version="0.4", entrypoint="run.py";
CREATE agent:random_number_agent SET name="random_number_agent", description="A simple agent for taking part in Keynesian beauty contests", author=user:naptha, url="https://github.com/NapthaAI/random_number_agent", type="package", version="0.3", entrypoint="run.py";
CREATE agent:test_personas SET name="test_personas", description="A simple test agent for testing personas", author=user:naptha, url="https://github.com/moarshy/test_personas", type="package", version="0.1", personas_urls=["https://huggingface.co/datasets/NapthaAI/market_agents_personas"], entrypoint="run.py";

-- ORCHESTRATORS
CREATE orchestrator:multiagent_chat SET name="multiagent_chat", description="Multi-agent network for chat", author=user:naptha, url="https://github.com/NapthaAI/multiagent_chat", type="package", version="0.12", entrypoint="run.py";
CREATE orchestrator:babyagi SET name="babyagi", description="Multi-agent network for running task-solving", author=user:naptha, url="https://github.com/NapthaAI/babyagi", type="package", version="0.2", entrypoint="run.py";
CREATE orchestrator:multiagent_debate SET name="multiagent_debate", description="A network of debating agents", author=user:naptha, url="https://github.com/NapthaAI/multiagent_debate", type="package", version="0.6", entrypoint="run.py";
CREATE orchestrator:keynesian_beauty_contest SET name="keynesian_beauty_contest", description="A network of agents that guess random numbers", author=user:naptha, url="https://github.com/NapthaAI/keynesian_beauty_contest", type="package", version="0.11", entrypoint="run.py";
CREATE orchestrator:napthaville_chat SET name="napthaville_chat", description="Multi-agent network for chat between characters in Napthaville", author=user:naptha, url="https://github.com/moarshy/napthaville_chat", type="package", version="0.4", entrypoint="run.py";
CREATE orchestrator:napthaville_move SET name="napthaville_move", description="Multi-agent network for social simulations in Napthaville", author=user:naptha, url="https://github.com/moarshy/napthaville_move", type="package", version="0.26", entrypoint="run.py";
CREATE orchestrator:multiagent_prediction SET name="multiagent_prediction", description="Multi-agent network for forecasting future events", author=user:naptha, url="https://github.com/NapthaAI/multiagent_prediction", type="package", version="0.2", entrypoint="run.py";

-- ENVIRONMENTS
CREATE environment:groupchat SET name="groupchat", description="Environment mechanism for group chat between agents.", author=user:naptha, url="https://github.com/NapthaAI/groupchat_environment", type="package", version="0.1", entrypoint="run.py";

-- PERSONAS
CREATE persona:market_agents_personas SET name="market_agents_personas", description="Personas for market agents", author=user:naptha, url="https://huggingface.co/datasets/NapthaAI/market_agents_personas", version="0.1";
CREATE persona:twitter_personas SET name="twitter_personas", description="Personas generated from twitter exports", author=user:naptha, url="https://huggingface.co/datasets/NapthaAI/twitter_personas", version="0.1";
CREATE persona:one_million_personas SET name="one_million_personas", description="Personas generated from the paper Scaling Synthetic Data Creation with 1M Personas", author=user:naptha, url="https://huggingface.co/datasets/proj-persona/PersonaHub", version="0.1";

-- NODES
CREATE node:naptha0 SET
    public_key="18837f9faec9a02744d308f935f1b05e8ff2fc355172e875c24366491625d932f36b34a4fa80bac58db635d5eddc87659c2b3fa700a1775eb4c43da6b0ec270d",
    ip="http://node.naptha.ai",
    port=7001,
    routing=null,
    ollama_models=["phi","gemma"],
    arch="x86_64",
    os="Linux",
    num_gpus=0,
    vram=0,
    ram=16758378496
;
--private_key="71565da40d9df9f9a19dec069bcf01e561395cdd792a5c3f59be734962247017"

CREATE node:naptha1 SET
    public_key="2c594f6e0de0633df89c0a231e17e886f0b79802fd611166333dc1bcb87e5f585bb13a41d2451521ac2a57d83b45dd8430970526b4ba718d6963b2f28c8f18d7",
    ip="http://node1.naptha.ai",
    port=7001,
    routing=null,
    ollama_models=["phi","gemma"],
    arch="x86_64",
    os="Linux",
    num_gpus=0,
    vram=0,
    ram=16758378496
;
--private_key="53a24990e661e48093502413b7926e80f5b577f809dd218759573815c9dc51e3"