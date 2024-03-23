import os
import torch
import torch.optim as optim
import torch.nn as nn
from torch.utils.data import DataLoader
from transformer import Transformer
from dataset import TranslationDataset
from logger import Logger

import numpy as np
import random
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from torch.utils.data import Dataset, DataLoader, random_split
from utils import parse_arguments, read_settings, calculate_bleu, calculate_nist


device = torch.device('cpu')
if torch.cuda.is_available():
    device = torch.device('cuda')

wandb_logger = Logger(f"inm706_translation_transformer", project='inm706_cwkk')
logger = wandb_logger.get_logger()

def train_epoch(train_dataloader, model, optimizer, criterion, use_gradient_clipping, plot_attention = False):
    model.train()
    total_loss = 0.0
    total_bleu_score = 0
    total_nist_score = 0

    for _, src, target_tensor in train_dataloader:
        optimizer.zero_grad()

        # Forward pass
        output = model(src, target_tensor)
        loss = criterion(output.view(-1, output.size(-1)), target_tensor.view(-1))

        # Backward pass and optimization
        loss.backward()
        if use_gradient_clipping:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1)
        optimizer.step()

        total_loss += loss.item()

         # Calculate BLEU score
        bleu_score = calculate_bleu(output, target_tensor)
        total_bleu_score += bleu_score

        # Calculate NIST score
        nist_score = calculate_nist(output, target_tensor)
        total_nist_score += nist_score

    return total_loss / len(train_dataloader), total_bleu_score / len(train_dataloader), total_nist_score / len(train_dataloader)

def validate_epoch(val_dataloader, model, criterion):
    model.eval()
    total_loss = 0.0
    total_bleu_score = 0
    total_nist_score = 0
    with torch.no_grad():
        for _, src, target_tensor in val_dataloader:
            output = model(src, target_tensor)
            loss = criterion(output.view(-1, output.size(-1)), target_tensor.view(-1))
            total_loss += loss.item()

             # Calculate BLEU score
            bleu_score = calculate_bleu(output, target_tensor)
            total_bleu_score += bleu_score

            # Calculate NIST score
            nist_score = calculate_nist(output, target_tensor)
            total_nist_score += nist_score

    return total_loss / len(val_dataloader), total_bleu_score / len(val_dataloader), total_nist_score / len(val_dataloader)

def train(train_dataloader, val_dataloader, model, n_epochs, criterion, use_gradient_clipping, learning_rate=0.0001, optimizer="adam" ):
    val_losses = [float("inf")]
    counter = 0

    if optimizer == "adam":
        optimizer = optim.Adam(model.parameters(), lr = learning_rate, betas=(0.9, 0.98), eps=1e-9)
    elif optimizer == "radam":
        optimizer = optim.RAdam(model.parameters(), lr = learning_rate)
    elif optimizer == "adamW":
        optimizer = optim.AdamW(model.parameters(), lr = learning_rate, weight_decay=1e-5)

    
    if criterion == "negative-log":
        criterion = nn.NLLLoss()
    elif criterion == "cross-entropy":
        criterion = nn.CrossEntropyLoss()

    for epoch in range(n_epochs):
        train_loss, train_bleu, val_bleu = train_epoch(train_dataloader, model, optimizer, criterion, use_gradient_clipping)
        val_loss, train_nist, val_nist = validate_epoch(val_dataloader, model, criterion)

        val_losses.append(val_loss)

        logger.log({'train_loss': train_loss, 'val_loss': val_loss})
        logger.log({"train_bleu": train_bleu, "validation_bleu": val_bleu})
        logger.log({"train_nist": train_nist, "validation_nist": val_nist})
        print(f"Epoch: {epoch} / {n_epochs}, Train Loss {train_loss}, Validation Loss {val_loss}, Train BLEU {train_bleu}, Validation BLEU {val_bleu}, Train NIST {train_nist}, Validation NIST {val_nist}")
        #print(f'Epoch [{epoch + 1}/{n_epochs}], Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}')

        if (val_loss + 0.01) < val_losses[epoch - 1]:
            # Restart patience (improvement in validation loss)
            counter = 0

            # Create checkpoint folder
            if not os.path.exists("checkpoints"):
                os.makedirs("checkpoints")

            # Save the model checkpoint
            checkpoint_name = f"checkpoint_latest.pth"
            checkpoint_path = os.path.join("checkpoints", checkpoint_name)
            torch.save({
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "train_bleu": train_bleu,
                "val_bleu": val_bleu,
                "train_nist": train_nist,
                "val_nist": val_nist,
            }, checkpoint_path)
        
        elif (val_loss + 0.01) > val_losses[epoch - 1]:
            # Add one to patience
            counter += 1
            # Patience reached, stop training (no significant improvement in validation loss after 5 epochs)
            if counter >= 5:
                break
    return


def main():
    # Set random seed for reproducibility
    randomer = 50
    torch.manual_seed(randomer)
    torch.cuda.manual_seed_all(randomer)
    random.seed(randomer)
    np.random.seed(randomer)

    generator = torch.Generator().manual_seed(randomer)

    # Read settings from the YAML file
    args = parse_arguments()
    settings = read_settings(args.config)

    # Access and use the settings as needed
    model_settings = settings.get('model', {})
    train_settings = settings.get('train', {})

    # Load the dataset and create DataLoader
    dataset = TranslationDataset(lang1='en', lang2='fr', reverse=True, max_seq_len=model_settings["max_seq_length"])
    batch_size = train_settings["batch_size"]
    n_epochs = train_settings["epochs"]

    # Split dataset into training and validation sets
    train_size = int(0.75 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size], generator = generator)

    train_dataloader = DataLoader(train_dataset, batch_size=batch_size)
    val_dataloader = DataLoader(val_dataset, batch_size=batch_size)

    # Create the Transformer model with encoder and decoder
    src_vocab_size = dataset.input_lang.n_words
    target_vocab_size = dataset.output_lang.n_words
    seq_length = dataset.max_seq_len
    hidden_size = model_settings["hidden_size"]

    model = Transformer(embed_dim=hidden_size, src_vocab_size=src_vocab_size,
                        target_vocab_size=target_vocab_size, seq_length=seq_length,
                        num_layers=model_settings["num_layers"], expansion_factor=model_settings["expansion_factor"],
                        n_heads=model_settings["n_heads"]).to(device)

    for p in model.parameters():
        if p.dim() > 1:
            nn.init.xavier_uniform_(p)

    #optimizer = optim.Adam(model.parameters(), lr=0.0001, betas=(0.9, 0.98), eps=1e-9)
    #criterion = nn.CrossEntropyLoss(ignore_index=0)
    use_gradient_clipping = True

    # Training loop
    train(train_dataloader, val_dataloader, model, n_epochs,  optimizer = train_settings["optimizer"], criterion = train_settings["loss_function"], use_gradient_clipping=True)

if __name__ == '__main__':
    main()
