# OpenAvatarChat2Dify  

了解到 OpenAvatarChat 项目的热度，社群中许多开发者希望将其接入 Dify 工作流以实现交互式数字人，本项目为此目标开发。



---

## 🔗 相关资源  

- **项目原地址**：  
[HumanAIGC-Engineering/OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)  

- **一键部署教程-来自十字鱼**：  
[B站视频：OpenAvatarChat 一键包更新4](https://www.bilibili.com/video/BV1uUNEzwEjh)  



---

## 🛠️ 使用教程  
### 步骤 1：克隆源代码  
```
git clone https://github.com/HumanAIGC-Engineering/OpenAvatarChat.git
```

# 使用教程
第一步：git clone项目源代码

第二步：找到/src/handlers/llm/openai_compatible/目录，将llm_handler_openai_compatible.py内容替换为本仓库中的llm_handler_openai_compatible_dify.py内容。

第三步：配置文件中相关内容（代码26-29行）
```
model_name: str = Field(default="e8df634e-fa77-4b65-ae8a-65e54142ab44")  # Dify 中部署的模型名称</br>
system_prompt: str = Field(default="请你扮演一个 AI 助手，用简短的对话来回答用户的问题，并在对话内容中加入合适的标点符号，不需要加入标点符号相关的内容")  # 保持原有系统提示</br>
api_key: str = Field(default="app-XHOpt25w1eOHNHoB4s6tSCli")  # 配置Dify的api_key</br>
api_url: str = Field(default="http://192.168.1.9/v1")  # 配置Dify的API服务器地址</br>
```
（代码最后一行）
```
response = requests.post('http://192.168.1.9/v1/chat-messages', headers=headers, json=payload) # 替换为你的dify的api地址</br>
```
## 可能出现的问题</br>
如果出现下方报错，将代码第20行和第45行的ChatHistory相关代码注释即可</br>
![image](https://github.com/user-attachments/assets/9e67b06d-0ebe-4527-85ec-320afdca0ad3)</br>
