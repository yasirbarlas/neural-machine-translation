import torch
import random
import numpy as np
from models import EncoderRNN, DecoderRNN
from dataset import TranslationDataset
from utils import parse_arguments, read_settings

device = torch.device("cpu")
if torch.cuda.is_available():
    device = torch.device("cuda")

print(device)

def indexesFromSentence(lang, sentence):
    return [lang.word2index[word] for word in sentence.split(" ")]

def tensorFromSentence(lang, sentence):
    EOS_token = 1
    indexes = indexesFromSentence(lang, sentence)
    indexes.append(EOS_token)
    return torch.tensor(indexes, dtype=torch.long, device=device).view(1, -1)

def evaluate(encoder, decoder, sentence, input_lang, output_lang):
    EOS_token = 1
    with torch.no_grad():
        input_tensor = tensorFromSentence(input_lang, sentence)

        encoder_outputs, encoder_hidden = encoder(input_tensor)
        decoder_outputs, decoder_hidden, decoder_attn = decoder(encoder_outputs, encoder_hidden)

        _, topi = decoder_outputs.topk(1)
        decoded_ids = topi.squeeze()

        decoded_words = []
        for idx in decoded_ids:
            if idx.item() == EOS_token:
                decoded_words.append("<EOS>")
                break
            decoded_words.append(output_lang.index2word[idx.item()])
    return decoded_words

def evaluate_randomly(encoder, decoder, dataset, n = 10):
    for i in range(n):
        pair = random.choice(dataset.pairs)
        print("Input:", pair[0])
        print("Target:", pair[1])
        output_words, _ = evaluate(encoder, decoder, pair[0], dataset.input_lang, dataset.output_lang)
        output_sentence = " ".join(output_words)
        print("Output:", output_sentence)
        print("")

def evaluating(encoder, decoder, input_tensor, output_lang):
    EOS_token = 1
    with torch.no_grad():
        encoder_outputs, encoder_hidden = encoder(input_tensor)
        decoder_outputs, decoder_hidden, decoder_attn = decoder(encoder_outputs, encoder_hidden)

        _, topi = decoder_outputs.topk(1)
        decoded_ids = topi.squeeze()

        decoded_words = []
        for idx in decoded_ids:
            if idx.item() == EOS_token:
                decoded_words.append("<EOS>")
                break
            decoded_words.append(output_lang.index2word[idx.item()])
    return decoded_words, decoder_attn

def evaluator(test_dataset = None, checkpoint = "checkpoint_latest.pth"):
    # Set random seed for reproducibility, intentionally not setting for GPU for faster performance
    randomer = 50
    torch.manual_seed(randomer)
    torch.cuda.manual_seed(randomer)
    random.seed(randomer)
    np.random.seed(randomer)

    # Get model settings
    args = parse_arguments()
    settings = read_settings(args.config)
    model_settings = settings.get("model", {})

    # Get dataset used in training for language vocabulary 
    #dataset = TranslationDataset(lang1 = "en", lang2 = "fr", max_seq_len = model_settings["max_seq_length"], reverse = False)

    # Initialise Encoder and Decoder objects
    encoder = EncoderRNN(5141, model_settings["hidden_dim"]).to(device)
    decoder = DecoderRNN(model_settings["hidden_dim"], 5801).to(device)

    # Gather model
    model = torch.load(f"checkpoints/{checkpoint}", map_location = device)

    # Split into Encoder and Decoder
    encoder.load_state_dict(model["encoder_state_dict"])
    decoder.load_state_dict(model["decoder_state_dict"])
    #encoder.load_state_dict(model["input_lang"])
    #decoder.load_state_dict(model["output_lang"])

    # Ensure the Encoder and Decoder are in evaluation mode
    encoder.eval()
    decoder.eval()

    # Randomly evaluate different sentences
    # v = evaluate_randomly(encoder, decoder, test_dataset, n = 100)

    # Display results
    # print(v)

    print(encoder)
    print("\n", decoder)
    #evaluate(encoder, decoder, "hello", "en", "fr")

evaluator()