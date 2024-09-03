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

CREATE category:custom_templates SET name="Custom Templates";
-- subcategories for Custom Templates
CREATE category:code_execution SET name="Code Execution", parent_categories=[category:custom_templates];
CREATE category:synthetic_data_generation SET name="Synthetic Data Generation", parent_categories=[category:custom_templates];
CREATE category:data_processing SET name="Data Processing", parent_categories=[category:custom_templates];
CREATE category:model_optimization SET name="Model Optimization", parent_categories=[category:custom_templates];
CREATE category:interactive_tools SET name="Interactive Tools", parent_categories=[category:custom_templates];
CREATE category:visualization SET name="Visualization", parent_categories=[category:custom_templates];
CREATE category:task_identification SET name="Task Identification", parent_categories=[category:custom_templates];
CREATE category:parallel_execution SET name="Parallel Execution", parent_categories=[category:custom_templates];
CREATE category:task_coordination SET name="Task Coordination", parent_categories=[category:custom_templates];
CREATE category:result_synthesis SET name="Result Synthesis", parent_categories=[category:custom_templates];
CREATE category:dynamic_adjustment SET name="Dynamic Adjustment", parent_categories=[category:custom_templates];
CREATE category:retrieval_augmented_generation SET name="Retrieval Augmented Generation", parent_categories=[category:custom_templates];

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
    password=crypto::argon2::generate("great-password")
;
CREATE user:marketagents SET 
    name="MarketAgents", 
    username="marketagents", 
    password=crypto::argon2::generate("great-password")
;
CREATE user:seller1 SET
    name = "Test Seller 1",
    username = "seller1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:creator1 SET
    name = "Test Creator 1",
    username = "creator1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:buyer1 SET
    name="Test Buyer 1",
    username="buyer1",
    password=crypto::argon2::generate("buyer1pass")
;
CREATE user:aiconsumer1 SET
    name = "AI Consumer 1",
    username = "aiconsumer1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:aideveloper1 SET
    name = "AI Developer 1",
    username = "aideveloper1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:nodeoperator1 SET
    name = "Node Operator 1",
    username = "nodeoperator1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:bittensor1 SET
    name = "Bittensor User",
    username = "bittensor1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:olas1 SET
    name = "Olas User",
    username = "olas1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:ocean1 SET
    name = "Ocean User",
    username = "ocean1",
    password = crypto::argon2::generate("great-password")
;
CREATE user:chainlink1 SET
    name = "Chainlink User",
    username = "chainlink1",
    password = crypto::argon2::generate("great-password")
;

-- ORGANIZATIONS
CREATE organization:naptha SET name="Naptha", image="https://richardblythman.github.io/image-api/algovera/algovera-whiteBackground.png?w=200&amp;h=200&amp;f=face", owner=user:seller1;
RELATE user:seller1->is_associated_with->organization:naptha;

-- TASKS 
CREATE lot:dateqa SET name="Subnet 1: Date Question", description="Get help answering a specific date-based question.", author=user:bittensor1;
CREATE lot:debugging SET name="Subnet 1: Code Debugging", description="Get help with debugging a coding problem.", author=user:bittensor1;
CREATE lot:instruction SET name="Subnet 1: Generic Instruction Following", description="Follow general instructions.", author=user:bittensor1;
CREATE lot:math SET name="Subnet 1: Math Solving", description="Get help solving a math problem.", author=user:bittensor1;
CREATE lot:qa SET name="Subnet 1: Question Answering", description="Answering questions.", author=user:bittensor1;
CREATE lot:summarization SET name="Subnet 1: Summarization", description="Summarizing text.", author=user:bittensor1;
CREATE lot:prediction SET name="Prediction Agents", description="Research and make predictions on Gnosis prediction markets.", author=user:olas1;
CREATE lot:governance SET name="Governance Agents", description="Read governance proposals and take part in voting.", author=user:olas1;
CREATE lot:predictoor SET name="Predictoor", description="Forecast prices of cryptocurrencies.", author=user:ocean1;
CREATE lot:developer SET name="Developer Assistant", description="Solve coding query with Chainlink libraries.", author=user:chainlink1;

CREATE lot:worldsim SET name="Virtual World Simulation", description="Run agents that simulate believable human behavior", author=user:naptha,
  request="syntax = \"proto3\";
  
  message Request {
        string prompt = 1;
  }",
  reply="syntax = \"proto3\";
  
  message Reply {
        string answer = 1;
  }"
;

RELATE lot:worldsim->is_associated_with->organization:naptha;
RELATE lot:worldsim->is_tagged->tag:general;
RELATE lot:worldsim->in_category->category:human_behavior;
RELATE lot:worldsim->has_license->license:apache2;

-- RFPs
CREATE auction:rfp1 SET 
    consigner=user:bittensor1,
    buy_it_now_price=10.0,    
    listing=lot:dateqa
;
CREATE auction:rfp2 SET
    consigner=user:bittensor1,
    buy_it_now_price=20.0,    
    listing=lot:debugging
;
CREATE auction:rfp3 SET
    consigner=user:bittensor1,
    buy_it_now_price=15.0,    
    listing=lot:instruction
;
CREATE auction:rfp4 SET
    consigner=user:bittensor1,
    buy_it_now_price=50.0,    
    listing=lot:math
;
CREATE auction:rfp5 SET
    consigner=user:bittensor1,
    buy_it_now_price=15.0,    
    listing=lot:qa
;
CREATE auction:rfp6 SET
    consigner=user:bittensor1,
    buy_it_now_price=25.0,    
    listing=lot:summarization
;
CREATE auction:rfp7 SET
    consigner=user:olas1,
    buy_it_now_price=50.0,    
    listing=lot:prediction
;
CREATE auction:rfp8 SET
    consigner=user:olas1,
    buy_it_now_price=50.0,    
    listing=lot:governance
;
CREATE auction:rfp9 SET
    consigner=user:ocean1,
    buy_it_now_price=25.0,    
    listing=lot:predictoor
;
CREATE auction:rfp10 SET
    consigner=user:chainlink1,
    buy_it_now_price=50.0,    
    listing=lot:developer
;
CREATE auction:auction1 SET consigner=user:seller1, buy_it_now_price=10.0, listing=lot:worldsim;
RELATE user:seller1->requests_to_publish->auction:auction1;

-- MODULEs
CREATE module:chat_aiflows SET name="Chat using AI Flows", description="A simple chat workflow using the AI Flows library", author=user:aideveloper1, url="https://huggingface.co/NapthaAI/chat_aiflows", type="template";
CREATE module:olas_prediction SET name="Predict Future Events", description="Workflow for making predictions about events", author=user:naptha, url="https://huggingface.co/NapthaAI/olas_prediction", type="template";
CREATE module:hello_world SET name="Hello World", description="A simple hello world workflow", author=user:creator1, url="https://github.com/NapthaAI/module_hello_world", type="template";
CREATE module:docker_hello_world SET name="Hello World Docker", description="A simple hello world app", author=user:creator1, url="https://hub.docker.com/_/hello-world", type="docker";
CREATE module:generate_image SET name="Generate Image Stable Diffusion", description="A simple workflow for generating an image from text", author=user:creator1, url="https://github.com/NapthaAI/module_generate_image", type="template";
CREATE module:create_profile_description SET name="Generate Profile Description", description="A simple workflow for writing a profile description based on key points", author=user:creator1, url="https://github.com/NapthaAI/module_create_profile_description", type="template";
CREATE module:image_to_image SET name="Image to Image Stable Diffusion", description="A simple workflow for generating an image from another image", author=user:creator1, url="https://github.com/NapthaAI/module_image2image", type="template";
CREATE module:chat SET name="Chat", description="A simple chat workflow", author=user:creator1, url="https://github.com/NapthaAI/chat", type="template";
CREATE module:multiplayer_chat SET name="Multiplayer Chat", description="A multiplayer chat app", author=user:naptha, url="https://huggingface.co/NapthaAI/multiplayer_chat", type="flow";
CREATE module:multi_olas_prediction SET name="Multi Olas Prediction", description="An implementation of multi olas prediction", author=user:naptha, url="https://huggingface.co/NapthaAI/multi_olas_prediction", type="flow";
CREATE module:babyagi SET name="Babyagi", description="A simple babyagi app", author=user:naptha, url="https://huggingface.co/NapthaAI/babyagi", type="flow";
CREATE module:babyagi_task_initiator SET name="Babyagi Task Initiator", description="A simple babyagi task initiator", author=user:naptha, url="https://huggingface.co/NapthaAI/babyagi_task_initiator", type="template";
CREATE module:babyagi_task_executor SET name="Babyagi Task Executor", description="A simple babyagi task executor", author=user:naptha, url="https://huggingface.co/NapthaAI/babyagi_task_executor", type="template";
CREATE module:babyagi_task_finalizer SET name="Babyagi Task Finalizer", description="A simple babyagi task finalizer", author=user:naptha, url="https://huggingface.co/NapthaAI/babyagi_task_finalizer", type="template";
CREATE module:napthaville_module SET name="Napthaville Module", description="implementation of Agentic game", author=user:naptha, url="https://github.com/moarshy/napthaville_module", type="template";
CREATE module:napthaville_chat SET name="Napthaville Chat", description="implementation of Napthaville chat between two personas", author=user:naptha, url="https://github.com/moarshy/napthaville_chat", type="flow";
CREATE module:napthaville_move SET name="Napthaville Move", description="implementation of Napthaville move between two personas", author=user:naptha, url="https://github.com/moarshy/napthaville_move", type="flow";
CREATE module:debate_agent SET name="Debate Agent", description="debating agent", author=user:marketagents, url="https://huggingface.co/NapthaAI/debate_agent", type="template";
CREATE module:debate_protocol SET name="Debate Protocol", description="debating protocol", author=user:marketagents, url="https://huggingface.co/NapthaAI/debate_protocol", type="flow";

CREATE organization:developer SET name="Developer Assistant", image="Solve coding query with Chainlink libraries.", owner=user:chainlink1;

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