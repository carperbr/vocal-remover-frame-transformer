# frame-transformer

This fork is mainly a research fork and will change frequently and there is like zeo focus on being user friendly. I am happy to answer any and all questions however.

Updating as its been a while. I am currently training the model found in libft/frame_transformer.py. This model is a more simple model than the original V1 model which was inspired by MMDENSELSTM. I will go into detail on the two versions (V2 kinda became V3 and I never trained it, V3 is more internal naming for my project I guess).

V1 - This neural network is the checkpoint down below and should work with the inference_thin2.py script with default settings; this is the neural network found in frame_transformer_thin.py. This neural network was inspired by the parent repo's MMDENSELSTM implementation. Instead of having a dense-net, this uses a single u-net where it downsamples only along the frequency dimension rather than both the frequency and temporal dimensions. The encoders and decoders in the u-net are called FrameEncoder and FrameDecoder modules. These downsample along the frequency axis as mentioned using a pre-norm residual multilayer perceptron setup with a parameterized identity. Each FrameEncoder along with the first FrameDecoder are preceded by a FrameTransformerEncoder. This module compresses the input into a single channel using a 1x1 conv2d with no normalization or non-linearities (this didn't seem to make a big impact). After that it uses a standard pre-norm transformer layer with multihead attention (it uses my multichannel multihead attention module but only a single channel so its equivalent to multihead attention in this case). The forward block has one small difference in that it uses squared ReLU for activation as mentioned in the Primer paper. Each FrameDecoder is followed by a FrameTransformerDecoder module. These modules work in the same manner as the FrameTransformerEncoder, however they take an additional skip connection as input - this skip connection is the attention map returned from the FrameTransformerEncoder. THe FrameTransformerDecoder follows a standard pre-norm transfomrer decoder architecture after that and uses the encoder attention map as memory in order to query against the pre-downsampled representation of the audio. After this everything is output using a single conv2d and sent through sigmoid as normal. Here is a new checkpoint for V1, I think it went for maybe 200k more optimization steps and improved a bit but admittedly I've lost interest in this version: https://mega.nz/file/C5pGXYYR#ndHuj-tYWtttoj8Y4QqAkAruvZDYcQONkTHfZoOyFaQ

V3 - This neural network is currently being trained and is doing significantly better than the V1 architecture. This architecture is quite a departure from the original repo and is fairly simple; it is no longer a u-net and instead can be viewed more as a hybrid between a resnet and a multichannel transformer. It starts with a conv2d to embed the spectrogram into a specified number of channels. After this, it sends the embedded representation through a series of v3 frame transformer encoders. V3 FrameTransformerEncoder modules are a bit different in how they work. They no longer compress the input representation. Instead, for the attention mechanism the V3 model uses the full embedding and processes that using multichannel layernorm and multichannel multihead attention. This uses a special kind of layer that I call MultichannelLinear layers which are my implementation of parallel position-wise linear layers using batched matrix multiplication. It allows each channel to learn its own linear layer, and includes an optional depthwise component to allow the channels to communicate or to allow changing the channel count. All projections in the attention mechanism use the depth-wise component in the multichannel linear layers despite not changing channel count in order to allow information transfer between them. From here, attention is carried out between the frames of each channel. The attention here uses a residual attention connection as seen in the RealFormer paper, and then is sent out through a multichannel linear output. Multichannel layernorm is just what it sounds like: layernorm where each channel learns its own element-wise affine parameters. The forward block of the V3 frame transformer encoder is where things get a bit different. Here, I use 3x3 conv2d and expand the channel count rather than expanding features which allows me to increase the channel count vs using multichannel linear here and expanding features. I will have a trained version of this one shortly.

I also have a weird BERT model I'm tinkering with that instantiates BERT in parallel using the multichannel transformer setup which is found in frame_transformer_bert.py. Even though the BERT transformer layers are not optimized, the input and output layers learn to remove vocals a fair amount without even fine-tuning the BERT modules. Once the BERT modules are fine-tuned, that will be 1.2 billion parameters or so. Should be interesting seeing as its already gotten reasonably well at extracting vocals with just the input multichannel linear, positional embedding, and output multichannel linear layers.

## References
- [1] Jansson et al., "Singing Voice Separation with Deep U-Net Convolutional Networks", https://ismir2017.smcnus.org/wp-content/uploads/2017/10/171_Paper.pdf
- [2] Takahashi et al., "Multi-scale Multi-band DenseNets for Audio Source Separation", https://arxiv.org/pdf/1706.09588.pdf
- [3] Takahashi et al., "MMDENSELSTM: AN EFFICIENT COMBINATION OF CONVOLUTIONAL AND RECURRENT NEURAL NETWORKS FOR AUDIO SOURCE SEPARATION", https://arxiv.org/pdf/1805.02410.pdf
- [4] Liutkus et al., "The 2016 Signal Separation Evaluation Campaign", Latent Variable Analysis and Signal Separation - 12th International Conference
- [5] Vaswani et al., "Attention Is All You Need", https://arxiv.org/pdf/1706.03762.pdf
- [6] So et al., "Primer: Searching for Efficient Transformers for Language Modeling", https://arxiv.org/pdf/2109.08668v2.pdf
- [7] Su et al., "RoFormer: Enhanced Transformer with Rotary Position Embedding", https://arxiv.org/abs/2104.09864
- [9] Asiedu et all., "Decoder Denoising Pretraining for Semantic Segmentation", https://arxiv.org/abs/2205.11423
- [10] He et al., "RealFormer: Transformer Likes Residual Attention", https://arxiv.org/abs/2012.11747