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
CREATE user:naptha1 SET 
    name="Naptha", 
    username="naptha1", 
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

CREATE lot:worldsim SET name="Virtual World Simulation", description="Run agents that simulate believable human behavior", author=user:naptha1,
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
CREATE module:chat SET name="Chat App", description="Multiplayer chat app for chatting with other nodes", author=user:aideveloper1, url="https://huggingface.co/NapthaAI/chat", type="template";
CREATE module:qa SET name="Question Answering RAG Workflow", description="Workflow for performing question answering with retrieval-augmented generation", author=user:naptha1, url="https://huggingface.co/NapthaAI/rag", type="template";
CREATE module:olas_prediction SET name="Prediction Workflow", description="Workflow for making predictions about events", author=user:naptha1, url="https://huggingface.co/NapthaAI/olas_prediction", type="template";
CREATE module:hello_world_daimon_template SET name="Hello World Daimon Template", description="A simple hello world app", author=user:creator1, url="", type="template";
CREATE module:docker_hello_world SET name="Docker Hello World", description="A simple hello world app", author=user:creator1, url="https://github.com/AlgoveraAI/hello_world_daimon_template", type="docker";
CREATE module:docker_cv2_image SET name="Docker CV2 Image", description="A simple app for image processing", author=user:creator1, url="", type="docker";
CREATE module:summary_daimon_template SET name="Summary Daimon Template", description="A simple app for summarizing text", author=user:creator1, url="https://github.com/AlgoveraAI/summary_daimon_template", type="template";
CREATE module:generate_image SET name="Generate Image Stable Diffusion", description="A simple module for generating an image from text", author=user:creator1, url="https://github.com/NapthaAI/module_generate_image", type="template";
CREATE module:create_profile_description SET name="Describe Daimon Template", description="A simple app for writing description based on key points", author=user:creator1, url="https://github.com/AlgoveraAI/describe_daimon_template", type="template";
CREATE module:sdi2i_daimon_template SET name="SDI2I Daimon Template", description="A simple app for image to image", author=user:creator1, url="https://github.com/AlgoveraAI/sdi2i_daimon_template", type="template";


CREATE organization:developer SET name="Developer Assistant", image="Solve coding query with Chainlink libraries.", owner=user:chainlink1;
