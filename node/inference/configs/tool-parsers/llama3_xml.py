import json
import re
from typing import Any, Sequence, Tuple, Union
from vllm.entrypoints.openai.protocol import (ChatCompletionRequest,
                                              DeltaFunctionCall, DeltaMessage,
                                              DeltaToolCall,
                                              ExtractedToolCallInformation,
                                              FunctionCall, ToolCall)
from vllm.entrypoints.openai.tool_parsers.abstract_tool_parser import (
    ToolParser, ToolParserManager)
from vllm.logger import init_logger
from vllm.transformers_utils.tokenizer import AnyTokenizer

logger = init_logger(__name__)


@ToolParserManager.register_module("functionary_31")
class Functionary32ToolParser(ToolParser):

    def __init__(self, tokenizer: AnyTokenizer):
        super().__init__(tokenizer)
        logger.warn("A streaming tool parser has not been implemented for functionary 3.2. Expect regular text "
                    "completions for streaming requests.")

    def extract_tool_calls(
            self, model_output: str,
            request: ChatCompletionRequest) -> ExtractedToolCallInformation:

        # if one or more function calls are present, handle them
        matches = re.findall(r"<function=([^>]+)>(.*?)</function>", model_output)
        if len(matches) == 0:
            return ExtractedToolCallInformation(
                tools_called=False,
                tool_calls=[],
                content=model_output
            )
        return ExtractedToolCallInformation(
            tools_called=True,
            tool_calls=[
                ToolCall(
                    type="function",
                    function=FunctionCall(
                        name=match[0],
                        arguments=match[1]
                    )
                ) for match in matches
            ]
        )


    def extract_tool_calls_streaming(
            self,
            previous_text: str,
            current_text: str,
            delta_text: str,
            previous_token_ids: Sequence[int],
            current_token_ids: Sequence[int],
            delta_token_ids: Sequence[int],
            request: ChatCompletionRequest,
    ) -> Union[DeltaMessage, None]:
        return DeltaMessage(content=delta_text)