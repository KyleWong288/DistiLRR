import argparse
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
from transformers import AutoTokenizer, GenerationConfig
from utils import *


NUM_SAMPLES = 5


# Given some (Q,A,E), returns a rationale on how to fix
def create_teacher_rationale(client, incorrect_code, error):
    prompt = create_rationale_prompt(incorrect_code, error)
    try:
        answer = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an intelligent expert at repairing code."},
                {"role": "user", "content": prompt} 
            ],
            max_tokens=400,
            seed=17
        )
        rationale = answer.choices[0].message.content
    except:
        rationale = ""
    return rationale


# Gets 1 generations, handles input encoding and output decoding
def predict(model, tokenizer, gen_config, prompt):
    input = tokenizer(prompt, truncation=False, return_tensors="pt").to(model.device)
    input_ids = input["input_ids"]
    raw_text_len = len(input_ids[0])
    
    res = ""
    with torch.no_grad():
        output = model.generate(
            **input,
            generation_config=gen_config,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
        res = tokenizer.decode(output[0][raw_text_len:], skip_special_tokens=True)
        while res.startswith("\n"):
            res = res[1:]
    return res


# Pipelined self repair with gpt rationales and base model code
def main():

    # torch.backends.cuda.enable_mem_efficient_sdp(False)
    # torch.backends.cuda.enable_flash_sdp(False)
    torch.cuda.empty_cache()
    set_random_seed(17)

    # Load model and set up gen config
    model = load_pretrained_model(args)
    generation_config = GenerationConfig(
        do_sample = True,
        temperature = args.temperature,
        top_p = args.top_p,
        max_new_tokens = args.max_new_tokens
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(DSC_MODEL_DICT[args.model_name])
    tokenizer.pad_token = tokenizer.eos_token

    # Load gpt client
    load_dotenv()
    client = OpenAI()
    repair_file = f"./repair/{args.dataset}/{args.model_name}/r0.json"

    # Loop for multiple repair rounds
    for round_num in tqdm(range(1, args.num_rounds+1)):

        # Load previous round data
        with open(repair_file, "r") as file:
            input_data = json.load(file)
        print("INPUT FILE:", repair_file)
    
        # Configure output file
        output_file = f"./output/{args.dataset}/{args.model_name}/icl/r{round_num}.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        print("OUTPUT FILE:", output_file)

        # Generate the repairs
        output = []
        for idx, sample in tqdm(enumerate(input_data)):
            answers = []
            for i in range(NUM_SAMPLES):
                if not sample["errors"][i]:
                    answers.append(sample["answers"][i])
                else:
                    prompt = create_repair_prompt_oneshot(sample["answers"][i], sample["errors"][i])
                    rationale = create_teacher_rationale(client, sample["answers"][i], sample["errors"][i])
                    prompt = prompt + rationale
                    answer = predict(model, tokenizer, generation_config, prompt)
                    answers.append(rationale + "\n" + answer)

            output.append({
                "id": sample["id"],
                "name": sample["name"],
                "prompt": sample["prompt"],
                "answers": answers,
                "test": sample["test"],
            })

            with open(output_file, 'w') as file:
                json.dump(output, file, indent=4)

        # Evaluate the new results
        eval_file = f"./eval/{args.dataset}/{args.model_name}/icl/r{round_num}.json"
        repair_file = f"./repair/{args.dataset}/{args.model_name}/icl/r{round_num}.json"
        evaluation_repair(output_file, eval_file, repair_file, NUM_SAMPLES, suffix="_icl")


# Generates rationales on how to fix with gpt, but code generation is still from base model
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", type=str, required=True, help="See DSC_MODEL_DICT for choices")
    parser.add_argument("--dataset", type=str, required=True, help="Testing dataset, either mbxp or humaneval")
    parser.add_argument("--num_rounds", type=int, required=True, help="The number of repair rounds")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling softmax temperature")
    parser.add_argument("--top_p", type=float, default=0.95, help="Nucleus filtering (top-p) before sampling (<=0.0: no filtering)")
    parser.add_argument("--max_new_tokens", type=int, default=800, help="The maximum number of tokens to generate")
    parser.add_argument("--load_in_8bit", action='store_true', default=True, help="load the model in 8 bits precision")
    args = parser.parse_args()
    
    main()

    print("DONE GENERATING!")