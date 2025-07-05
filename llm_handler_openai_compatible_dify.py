

import json


import os
import re
from typing import Dict, Optional, cast
from loguru import logger
from pydantic import BaseModel, Field
from abc import ABC
from openai import OpenAI
from chat_engine.contexts.handler_context import HandlerContext
from chat_engine.data_models.chat_engine_config_data import ChatEngineConfigModel, HandlerBaseConfigModel
from chat_engine.common.handler_base import HandlerBase, HandlerBaseInfo, HandlerDataInfo, HandlerDetail
from chat_engine.data_models.chat_data.chat_data_model import ChatData
from chat_engine.data_models.chat_data_type import ChatDataType
from chat_engine.contexts.session_context import SessionContext
from chat_engine.data_models.runtime_data.data_bundle import DataBundle, DataBundleDefinition, DataBundleEntry
from handlers.llm.openai_compatible.chat_history_manager import ChatHistory, HistoryMessage
import requests



class LLMConfig(HandlerBaseConfigModel, BaseModel):
    model_name: str = Field(default="e8df634e-fa77-4b65-ae8a-65e54142ab44")  # Dify 中部署的模型名称
    system_prompt: str = Field(default="请你扮演一个 AI 助手，用简短的对话来回答用户的问题，并在对话内容中加入合适的标点符号，不需要加入标点符号相关的内容")  # 保持原有系统提示
    api_key: str = Field(default="app-XHOpt25w1eOHNHoB4s6tSCli")  # 配置Dify的api_key
    api_url: str = Field(default="http://192.168.1.9/v1")  # 配置Dify的API服务器地址
    enable_video_input: bool = Field(default=False)

class LLMContext(HandlerContext):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.config = None
        self.local_session_id = 0
        self.model_name = None
        self.system_prompt = None
        self.api_key = None
        self.api_url = None
        self.client = None
        self.input_texts = ""
        self.output_texts = ""
        self.current_image = None
        self.history = ChatHistory()
        self.enable_video_input = False
    def init_client(self):
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_url,
            # 添加 Dify 所需的自定义头部（如果需要）
            default_headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
        )

class HandlerLLM(HandlerBase, ABC):
    def __init__(self):
        super().__init__()

    def get_handler_info(self) -> HandlerBaseInfo:
        return HandlerBaseInfo(
            config_model=LLMConfig,
        )

    def get_handler_detail(self, session_context: SessionContext,
                           context: HandlerContext) -> HandlerDetail:
        definition = DataBundleDefinition()
        definition.add_entry(DataBundleEntry.create_text_entry("avatar_text"))
        inputs = {
            ChatDataType.HUMAN_TEXT: HandlerDataInfo(
                type=ChatDataType.HUMAN_TEXT,
            ),
            ChatDataType.CAMERA_VIDEO: HandlerDataInfo(
                type=ChatDataType.CAMERA_VIDEO,
            ),
        }
        outputs = {
            ChatDataType.AVATAR_TEXT: HandlerDataInfo(
                type=ChatDataType.AVATAR_TEXT,
                definition=definition,
            )
        }
        return HandlerDetail(
            inputs=inputs, outputs=outputs,
        )

    def load(self, engine_config: ChatEngineConfigModel, handler_config: Optional[BaseModel] = None):
        if isinstance(handler_config, LLMConfig):
            if handler_config.api_key is None or len(handler_config.api_key) == 0:
                error_message = 'api_key is required in config/xxx.yaml, when use handler_llm'
                logger.error(error_message)
                raise ValueError(error_message)

    def create_context(self, session_context, handler_config=None):
        if not isinstance(handler_config, LLMConfig):
            handler_config = LLMConfig()
        context = LLMContext(session_context.session_info.session_id)
        context.model_name = handler_config.model_name
        context.system_prompt = {'role': 'system', 'content': handler_config.system_prompt}
        context.api_key = handler_config.api_key
        context.api_url = handler_config.api_url
        context.enable_video_input = handler_config.enable_video_input
        
        context.client = OpenAI(
            # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
            api_key=context.api_key,
            base_url=context.api_url,
            timeout=30  # 添加超时参数，单位为秒
        )
        return context
    
    def start_context(self, session_context, handler_context):
        pass

    def handle(self, context: HandlerContext, inputs: ChatData,
               output_definitions: Dict[ChatDataType, HandlerDataInfo]):
        output_definition = output_definitions.get(ChatDataType.AVATAR_TEXT).definition
        context = cast(LLMContext, context)
        text = None
        if inputs.type == ChatDataType.CAMERA_VIDEO and context.enable_video_input:
            file_to_upload = inputs.data.get_main_data()
            user_id = inputs.data.get_meta("speech_id")
            if user_id is None:
                user_id = context.session_id
            files = {
                'file': ('filename', file_to_upload)
            }
            data = {
                'user': user_id
            }
            headers = {
                'Authorization': f'Bearer {context.api_key}',
                'Content-Type': 'image/*'
            }
            upload_url = f'{context.api_url}/files/upload'
            try:
                upload_response = requests.post(upload_url, headers=headers, data=data, files=files)
                upload_response.raise_for_status()
                logger.info('文件上传成功')
            except requests.exceptions.RequestException as e:
                logger.error(f'文件上传失败: {e}')
            return
        elif inputs.type == ChatDataType.HUMAN_TEXT:
            text = inputs.data.get_main_data()
        else:
            return
        speech_id = inputs.data.get_meta("speech_id")
        if (speech_id is None):
            speech_id = context.session_id

        if text is not None:
            context.input_texts += text

        text_end = inputs.data.get_meta("human_text_end", False)
        if not text_end:
            return

        chat_text = context.input_texts
        chat_text = re.sub(r"<\|.*?\|>", "", chat_text)
        if len(chat_text) < 1:
            return
        logger.info(f'llm input {context.model_name} {chat_text} ')
        current_content = context.history.generate_next_messages(chat_text, 
                                                                 [context.current_image] if context.current_image is not None else [])
        logger.debug(f'llm input {context.model_name} {current_content} ')

        # 构造 Dify 请求体
        headers = {
            'Authorization': f'Bearer {context.api_key}',
            'Content-Type': 'application/json'
        }
        logger.info(f'二次请求时，请求头: {{headers}}')
        logger.info(f"请求头: {headers}")
        # 尝试获取会话 ID
        conversation_id = context.history.get_conversation_id() if hasattr(context.history, 'get_conversation_id') else ''
        # 添加会话 ID 有效性检查和日志记录
        if conversation_id:
            logger.info(f'获取到的会话 ID: {conversation_id}')
        else:
            logger.warning('未获取到有效的会话 ID')
        payload = {
            'query': chat_text,
            'inputs': {},
            'response_mode': 'streaming',
            'user': speech_id,
            'files': [],
            'auto_generate_name': True
        }
        logger.info(f'二次请求时，请求体: {{payload}}')
        logger.info(f"请求体: {payload}")
        request_url = f'{context.api_url}/chat-messages'
        logger.info(f'二次请求时，请求 URL: {{request_url}}')
        logger.info(f"请求 URL: {request_url}")
        try:
            # 发送 POST 请求
            response = requests.post(request_url, headers=headers, json=payload, stream=True)
            response.raise_for_status()

            if payload['response_mode'] == 'streaming':
                for line in response.iter_lines():
                    if line:
                        line = line.lstrip(b'data: ').decode('utf-8')
                        try:
                            data = json.loads(line)
                            event = data.get('event')
                            if event == 'message':
                                output_text = data.get('answer', '')
                                context.output_texts += output_text
                                logger.info(output_text)
                                output = DataBundle(output_definition)
                                output.set_main_data(output_text)
                                output.add_meta("avatar_text_end", False)
                                output.add_meta("speech_id", speech_id)
                                yield output
                            elif event == 'message_end':
                                # 更新会话 ID
                                new_conversation_id = data.get('conversation_id')
                                if new_conversation_id:
                                    context.history.set_conversation_id(new_conversation_id)
                                context.history.add_message(HistoryMessage(role="avatar", content=context.output_texts))
                                context.output_texts = ''
                                logger.info('avatar text end')
                                end_output = DataBundle(output_definition)
                                end_output.set_main_data('')
                                end_output.add_meta("avatar_text_end", True)
                                end_output.add_meta("speech_id", speech_id)
                                yield end_output
                            elif event == 'error':
                                logger.error(f"请求出错: {data.get('message')}")
                                # 获取建议问题列表
                                message_id = conversation_id  # 假设使用会话 ID 作为 message_id
                                user_id = speech_id  # 假设使用 speech_id 作为用户标识
                                suggested_url = f'{context.api_url}/messages/{message_id}/suggested?user={user_id}'
                                suggested_headers = {
                                    'Authorization': f'Bearer {context.api_key}',
                                    'Content-Type': 'application/json'
                                }
                                try:
                                    suggested_response = requests.get(suggested_url, headers=suggested_headers)
                                    suggested_response.raise_for_status()
                                    suggested_questions = suggested_response.json()
                                    # 将建议问题整合到输出中
                                    end_output.add_meta("suggested_questions", suggested_questions)
                                except requests.RequestException as e:
                                    logger.error(f'获取建议问题列表失败: {e}')
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                data = response.json()
                if data.get('event') == 'message':
                    output_text = data.get('answer', '')
                    context.output_texts = output_text
                    context.history.add_message(HistoryMessage(role="avatar", content=context.output_texts))
                    output = DataBundle(output_definition)
                    output.set_main_data(output_text)
                    output.add_meta("avatar_text_end", True)
                    output.add_meta("speech_id", speech_id)
                    yield output

        except requests.RequestException as e:
            logger.error(f"请求发生错误: {e}")

        context.current_image = None
        context.input_texts = ''
        context.output_texts = ''
        # 删除未定义的 completion 相关代码，保留流式处理逻辑
        # 删除未定义的 completion 相关代码，保留流式处理逻辑
        response = requests.post('http://192.168.1.9/v1/chat-messages', headers=headers, json=payload)
        
        context.history.add_message(HistoryMessage(role="avatar", content=context.output_texts))
        context.output_texts = ''
        logger.info('avatar text end')
        end_output = DataBundle(output_definition)
        end_output.set_main_data('')
        end_output.add_meta("avatar_text_end", True)
        end_output.add_meta("speech_id", speech_id)
        yield end_output

    def destroy_context(self, context: HandlerContext):
        pass


# 构造请求头和请求体
headers = {
    'Authorization': 'Bearer {api_key}',
    'Content-Type': 'application/json'
}
payload = {
    'inputs': {},
    'query': 'What are the specs of the iPhone 13 Pro Max?',
    'response_mode': 'streaming',
    'conversation_id': '',
    'user': 'abc-123',
    'files': [
        {
            'type': 'image',
            'transfer_method': 'remote_url',
            'url': 'https://cloud.dify.ai/logo/logo-site.png'
        }
    ]
}

# 发送 POST 请求
response = requests.post('http://192.168.1.9/v1/chat-messages', headers=headers, json=payload)

