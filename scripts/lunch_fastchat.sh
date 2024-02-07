mkdir -p output
export CUDA_VISIBLE_DEVICES=0

# launch the controller
nohup python3 -m fastchat.serve.controller > output/controller.out &

# launch the model worker(s)(等待前一步完成)
# model_path="/opt/llm/vicuna-13b-v1.3/"
# model_name="vicuna-13b-v1.3"
## huggingface
# nohup python3 -m fastchat.serve.model_worker --model-path ${model_path} > output/model_workers.out &
## vllm
# nohup python3 -m fastchat.serve.vllm_worker --model-path ${model_path} > output/vllm_workers.out &

# NOTE: 需要根据`model_name`选择对话模板，如果未指定或不匹配则使用默认模板（vicuna），因此使用qwen等模型时不匹配
model_path="/opt/llm/qwen-14B-Chat/"
model_name="qwen-14b-chat"
# model_path="/opt/llm/Yi-34B-Chat/"
# model_name="yi-7b-chat"
nohup python3 -m fastchat.serve.model_worker --model-path ${model_path} --seed 42 \
    --host 0.0.0.0 --port 21002 --worker-address http://0.0.0.0:21002 > output/model_workers.out &
# nohup python3 -m fastchat.serve.vllm_worker --model-path ${model_path} --seed 42 \
#     --host 0.0.0.0 --port 21002 --worker-address http://0.0.0.0:21002 > output/model_workers.out &

# test the model
# python3 -m fastchat.serve.test_message --model-name ${model_name}

# launch the gradio web server (等待前两步完成)
nohup python3 -m fastchat.serve.gradio_web_server > output/web_server.out &

# launch the openai api server
nohup python3 -m fastchat.serve.openai_api_server \
    --host 0.0.0.0 --port 8000 > output/openai_api_server.out &

# ps -ef | grep fastchat
 
