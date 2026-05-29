from indextts.infer_v2 import IndexTTS2
from glob import glob
import os
import pandas as pd

tts = IndexTTS2(
    cfg_path="/data/nvme2/model/IndexTeam/IndexTTS-2/config.yaml",
    model_dir="/data/nvme2/model/IndexTeam/IndexTTS-2/",
    use_fp16=True,
    use_cuda_kernel=True,
    use_deepspeed=True,
)


# def test():
#     text = "啊,啊~啊~嗯~啊~嗯"
#     for i in range(2):
#         tts.infer(
#             spk_audio_prompt="examples/文字4-嗯6-原音频.wav",
#             text=text,
#             output_path="gen.wav",
#             verbose=False,
#         )


text_path_data = pd.read_excel("/root/code/temp/index-tts-main/examples/5/temp2.xlsx")[
    ["text", "path"]
]
texts = [
    "嗯啊啊哦啊啊干死我",
    "哦啊哦哦嗯要被干死了",
    "嗯嗯哦哦啊啊干死我",
    "啊哦哦嗯啊干晕了",
    "啊啊哦哦嗯啊要被干坏了",
    "哦哦嗯啊哦使劲干我",
    "哦啊嗯哦啊被干坏了",
    "哦哦啊嗯啊要被干晕了",
    "哦啊啊嗯啊把骚逼再干大一点",
    "啊嗯哦啊嗯想要接着干",
    "啊嗯啊嗯哦哦水要流干了",
    "啊嗯哦哦啊啊往死里干我",
    "嗯啊啊哦嗯嗯被老公干死",
    "啊嗯啊哦哦啊快干我",
    "哦哦啊嗯嗯人家榨干",
    "嗯啊嗯啊哦哦猛猛干",
    "啊啊嗯啊啊努力干我",
    "啊啊嗯啊啊干死我",
    "嗯啊嗯哦啊嗯随便干我",
    "啊嗯哦啊啊嗯干死我了",
    "嗯哦嗯啊啊被干翻了",
    "啊哦哦啊啊干死我",
    "啊嗯啊啊嗯操死小穴吧",
    "哦哦嗯啊嗯操飞了小穴",
    "嗯啊哦啊嗯操烂小穴啊",
    "嗯啊哦啊嗯被操晕了啊",
    "啊啊嗯嗯啊被操裂了啊",
    "啊啊哦啊嗯操烂小骚穴",
    "啊嗯嗯啊嗯扶腰猛操逼",
    "啊哦啊嗯嗯狠狠操弄我",
    "嗯嗯啊啊嗯大力操我啊",
    "嗯啊哦啊嗯把它操烂掉",
    "哦啊啊嗯嗯掰开腿操逼",
    "啊啊嗯哦嗯操我别停啊",
    "啊啊嗯啊嗯要被操晕了",
    "嗯嗯哦哦啊啊快操烂小骚逼",
    "嗯啊啊嗯嗯快把骚逼操烂",
    "嗯嗯哦哦啊操死我",
    "腰啊啊哦哦啊继续操",
    "嗯嗯哦嗯嗯操死我啊",
    "嗯嗯哦嗯嗯啊小骚逼都被操软了",
    "嗯嗯哦哦啊要被操肿了",
    "哦哦啊嗯嗯操死我",
    "啊啊嗯嗯啊操得好撑啊",
    "啊啊嗯哦哦骚逼被你操红了",
    "啊啊嗯嗯哦哦操喷出来了",
    "嗯嗯啊啊哦快被你操晕了",
    "哦哦啊嗯嗯加快车速操",
    "啊嗯嗯啊啊骚穴被操肿了",
    "嗯嗯啊嗯嗯啊求求你操死我",
    "嗯嗯啊哦哦越操越爱了",
    "哦哦嗯啊啊要被操死了",
    "嗯嗯哦哦啊啊操死我宝贝",
    "哦哦啊啊嗯快来操死小母狗",
    "啊嗯啊嗯嗯要被操坏了",
    "啊啊嗯嗯啊狠狠的操我",
    "啊啊嗯啊嗯边操边摸大腿",
    "嗯嗯啊啊嗯主人操死我",
]


def batch_tts():
    for audio_file in glob("examples/ok/*.WAV"):
        wavname = audio_file.split("/")[-1].replace(".wav", "")
        output = f"output/{wavname}"
        os.makedirs(output, exist_ok=True)
        for i, text in enumerate(texts):
            # if len(text) < 6:
            #     continue
            tts.infer(
                spk_audio_prompt=audio_file,
                text=text,
                output_path=f"{output}/gen{i}.wav",
                verbose=True,
            )
            print(
                f"========={wavname}==========[{i}/{len(texts)}]========================"
            )


if __name__ == "__main__":
    # test()
    batch_tts()


# CUDA_VISIBLE_DEVICES=5 python ttsTestone.py
