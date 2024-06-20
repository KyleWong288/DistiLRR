RUN_NAME="e5-lr5"
MODEL_NAME="mistral-7b"
CHECKPOINT="checkpoint-250"
DATASET="mbxp"
CUDA_VISIBLE_DEVICES=2 python gen_repair.py \
    --run_name $RUN_NAME \
    --model_name $MODEL_NAME \
    --dataset $DATASET \
    --checkpoint_path "./finetuned_models/$MODEL_NAME/$RUN_NAME/$CHECKPOINT" \
    --num_rounds 4 \