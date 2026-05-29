from indextts.infer_v2 import IndexTTS2
import pandas as pd
import os
import numpy as np

# 1. 加载数据
text_path_data = pd.read_excel("depthText2Path2.xlsx")[["text", "path", "tempPath"]]

# 2. 初始化 TTS 模型
tts = IndexTTS2(
    cfg_path="/data/nvme2/model/IndexTeam/IndexTTS-2/config.yaml",
    model_dir="/data/nvme2/model/IndexTeam/IndexTTS-2/",
    use_fp16=True,
    use_cuda_kernel=True,
    use_deepspeed=True,
)

# 3. 获取音频提示文件列表
wav_dir = "/root/code/index-tts/examples/gen"
audio_prompts = [
    os.path.join(wav_dir, f)
    for f in os.listdir(wav_dir)
    if f.endswith(".wav") or f.endswith(".WAV")
]
audio_prompts.sort()

num_prompts = len(audio_prompts)
if num_prompts == 0:
    raise FileNotFoundError(f"在目录 {wav_dir} 中未找到任何 .wav 文件！")

# 4. 将 DataFrame 数据平均分成 num_prompts 份
# np.array_split 会处理无法整除的情况，确保数据不重不漏
data_chunks = np.array_split(text_path_data, num_prompts)


def batch_tts():
    total_count = 0
    # 外层循环：遍历每一个音频提示文件
    for idx, audio_file in enumerate(audio_prompts):
        print(audio_file)
        current_chunk = data_chunks[idx]  # 获取该音频对应的文本切片

        print(f"\n>>> 开始处理音频组 [{idx + 1}/{num_prompts}]")
        print(f">>> 使用 Prompt 音频: {os.path.basename(audio_file)}")
        print(f">>> 该组任务数: {len(current_chunk)} 条")
        print("-" * 50)
        texe_list = []
        path_list = []
        temp_list = []
        # 内层循环：用当前的音频跑完它分配到的所有文本
        for _, row in current_chunk.iterrows():
            text = row["text"]
            path = row["path"]
            temp_path = row["tempPath"]
            if not os.path.isfile(temp_path):
                tts.infer(
                    spk_audio_prompt=audio_file,
                    text=text,
                    output_path=temp_path,
                    verbose=True,
                )
            texe_list.append(text)
            path_list.append(path)
            temp_list.append(temp_path)

            total_count += 1
            print(
                f"==================进度: {total_count}/{len(text_path_data)} | 已生成: {temp_path}"
            )
        level_data = pd.DataFrame()
        level_data["text"] = texe_list
        level_data["temp"] = temp_list
        level_data["path"] = path_list
        level_data.to_excel(f"{audio_file.lower().replace('wav', 'xlsx')}", index=False)

    print("\n================ 所有任务处理完毕！ ================")
    print(audio_prompts)


# 执行
if __name__ == "__main__":
    batch_tts()
