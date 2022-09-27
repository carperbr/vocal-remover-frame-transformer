# frame-transformer

This fork is mainly a research fork, although I think I've converged on a solid architecture that applies transformers to audio in a meaningful manner.

Yet another architecture change. New architecture is in frame_transformer3.py. Had a bit of inspiration after seeing OpenAI's whisper and restructured the frame transformer to be similar while still using multichannel linear layers. The new architecture is more simple; it consists of a frame encoder and a frame decoder. The frame encoder will embed the spectrogram into a one quarter of the fft size, so n_fft of 2048 gets each frame embedded into 512 features. The encoder uses multichannel linear layers in the form of a residual block. After encoding, this architecture makes use of what I call a multichannel transformer. Multichannel transformers utilize the multichannel linear module which is my implementation of parallel position-wise linear layers with a depth-wise component to allow for parallel transformers. Aside from being extended into the channel dimension, this architecture follows the Primer paper's findings and uses squared ReLU for activation as well as 1xN convolutions after the multichannel linear projections in the attention mechanism; this is simply an extension of the Primer's use of conv1d into 2d. The decoder is simply the opposite of the encoder, it expands from n_fft // 4 back to n_fft // 2 features. Preliminary tests point to this working quite well while also being fast to train. I should have checkpoints soon, however my focus at this very moment is using the frame transformer in a denoising diffusion setup.

The vocal remover I'm calling a frame transformer, or more specifically a convolutional multichannel frame primer. Multichannel transformers are an extension of transformers into the channel dimension; to make this possible without absurd delays in training, I created a layer that I call multichannel linear that consists of a position-wise transform for each channel as well as a depth-wise transform to increase/reduce channels which relies on batched matrix multiplication and a shared weight tensor for parallel linear layers. For encoding frames and decoding frames, 7x1 convolutions are used in a standard two layer perceptron setup as in the transformer architecture. These expand and shrink the number of channels respectively while also downsampling along the frequency axis.

I have added a working autoregressive convolutional multichannel frame primer which uses the traditional transformer architecture. The u-net in the autoregressive variant is used for encoding the source and target sequence, and then decoding the 'translated' target sequence using the encoded source sequence as a skip connection. I am currently training a version with 12 channels which gets expanded into 384 channels in the core of the u-net. There are 6 multichannel transformer encoders and 6 multichannel transformer decoders which means there are 384 parallel transformer encoders per layer and 384 parallel transformer decoders per layer, coming out to 4608 transformer layers in total counting both width and depth. It uses causal convolutions for the frame encoders and frame decoders as well as in the attention mechanism.

Currently training a convolutional frame primer variant that is doing quite well; currently training with 6 channels which means 6 parallel transformer layers kick things off, then 12, 24, 48, 96, and finally 192 parallel transformer layers at the core of the u-net. I'm currently only using one head of attention per channel, however I will be testing out multiple heads in another run once this variant is fully trained as I suspect that will probably help (it also increases memory consumption quite a bit and lowers the number of dimensions per head to very small number of features, but given this occurs in the deep portion of the u-net where features are more abstract this makes sense imo).

Currently at 161,319 optimization steps with my current training session which at its deepest has 192 parallel transformer layers and still learning steadily, videos below show the current convolutional multichannel frame primer in use: 

This video compares the current model at a cropsize of 256 and a cropsize of 2080, clearly showing that the model is contextualizing audio: https://www.youtube.com/watch?v=9Q9v4Okbvs4

This video compares the baseline cascaded net from the parent repo with my architecture; the first half is cascaded net while the second half is the convolutional frame primer: https://www.youtube.com/watch?v=92hAweHzpis

Example of conversion with frame transformer at 150k optimization steps with a batch size of 16 (300 million parameters):
https://www.youtube.com/watch?v=yjd0VilzQXA 

Currently training a multichannel primer, will probably stick with that as it seems to be doing much better now that I removed the depth-wise component of the transformer modules. I use a separable 1x7 convolution which is equivalent to their use of separable 1d convolutions extended into 2d.

## Architecture Diagram ##
### Conv Frame Primer ###
![image](https://user-images.githubusercontent.com/30326384/189788070-fcf4184e-1835-44ab-9e08-0d553731f3c5.png)

### Frame Primer ###  
![image](https://user-images.githubusercontent.com/30326384/189513744-43eeeb70-ecf5-42ef-8f62-d482fc7ae8e7.png)

### Frame Transformer ###
![image](https://user-images.githubusercontent.com/30326384/188557676-af84b966-007a-430c-a10a-1d26ebfda242.png)

This neural network at its core relies on a type of layer that I refer to as a multichannel linear layer. This has two weight tensors: a 3d weight tensor which is the weight matrices for each channels position-wise transform and then a 2d weight matrix for the depth-wise transform. This allows each channel to have its own position-wise linear layer that is applied to each frame while taking advantage of batched matrix multiplication. Compared to conv1d, this is around 2x faster when using smaller numbers of channels and far faster when using many channels/parallel linear layers.

This architecture is actually able to be applied to machine translation as well, however I haven't tried that yet. I will be uploading a translation training script as well as a midi generation script soon, though not totally sure how they'll compete with autoregressive transformers yet. My hope is that the multiple channels allows it to work in one pass even on inference, but we shall see soon. I am curious to see how it does with translation, given that it effectively rephrases the transformer problem in a weird way such that it would allow for non-autoregressive inference which would obviously be very fast if it worked. My original attempt at applying just the transformer architecture without any downsampling failed pretty miserably without removing any vocals which makes me wonder how it would work with downsampling embedding vectors. Seems to me like audio -> midi transcription is another area where this could be useful.

This fork also makes use of a dataset I refer to as voxaug in order to satisfy the transformers need for large amounts of data. This dataset randomly selects from a library of instrumental music and a library of vocal tracks and mixes them together for the neural network to train on. This has the benefit of inflating data exponentially as well as ensuring data is perfect for the removal process. To an extent you could view this as self-supervised learning in that its learning to remove a mask of vocals. My instrumental dataset consists of 30.88 days worth of music while my vocal stem library consists of 1416 full song vocal tracks. I will be uploading checkpoints for a 357,493,618 parameter model after it trains for a few days.

Current training at a cropsize of 256; orange at the bottom is on 10 seconds of audio, others are at 5 seconds. Will be increasing to 10 seconds with the current version after I reach 150k steps which should see it overtake the orange which is my best run yet with the convolutional varant. Green is a run with the convolutional variant at a cropsize of 256. Comparing with the parent repo, at around 62459k steps it was competitive with the original with a more full mix, so it should be interesting to see where this is now at 108k steps and eventually once I get to 250k ![image](https://user-images.githubusercontent.com/30326384/188479869-a7608716-4038-4afe-8c90-9c983a6e9ee4.png)

I might let this train for longer, however I have the max step count set to 350k which is 150k less than the primer architecture and 650k less than BERT. I suspect once trained to matching number of steps this architecture will be able to be finetuned fairly well for downstream tasks such as remastering.


## Module Descriptions ##

* **FrameTransformer** - The core of the neural network. This consists of a series of encoders and decoders, with encoders defined as frame_transformer_encoder(frame_encoder(x)) and decoders defined as frame_transformer_decoder(frame_decoder(x, skip), skip). It also includes an output depthwise linear layer in the form of a weight matrix.

* **MultichannelLinear** - This was my solution to having parallel linear layers. Instead of having individual linear layers, I compressed them into a single weight matrix with a channel dimension and make use of batched matrix multiplication. It also includes a depth-wise linear layer for increasing channel count (compression of frequency axis and expansion of channels is still necessary for this to learn well, although it seems to have less of a reliance on channels than a convolutional neural network).

* **FrameNorm** - This applies layer norm to each frame; each channel has its own element-wise affine parameters.

* **FrameEncoder** - position-wise encoder for each frame responsible for downsampling and expansion of channels. This consists of a residual block made from multichannel linear layers to allow for each channel to learn its own position-wise linear layer. It takes inspiration from the transformer architecture and uses residual blocks in that style - linear2(activation(linear1(norm(x)))). For activation this uses squared ReLU as in the primer paper.

* **FrameDecoder** - position-wise decoder for each frame responsible for upsampling and reduction of channels. This consists of two residual blocks; the first allows each channel to learn its own position-wise and depth-wise residual block for upsampling frames, and the second residual block integrates the skip connection by concatenating it with the output of the first block and reducing it back to out_channels with a position-wise and depth-wise multichannel linear layer. For activation this uses squared ReLU as in the primer paper.

* **MultichannelMultiheadAttention** - This module is an extension of multihead attention for multiple channels. Each channel learns its own projection layers. The projections use multichannel linear layers; this no longe rmakes use of convolutions as in the primer architecture, though once I train this version out I'll try a variant with 1x3 kernel convolutions (1x9 completely broke training so yeah, not fully convinced convolutions are useful for this problem).

* **FrameTransformerEncoder** - This is the transformer encoder module. It is a pre-norm variant of the transformer encoder architecture which makes use of multichannel multihead attention and multichannel linear layers to allow for parallel transformers effectively; aside from that it is the same as typical transformers. As in the primer architecture, this makes use of squared relu for activation.

* **FrameTransformerDecoder** - This is the transformer decoder module. It is a pre-norm variant of the transformer decoder architecture which makes use of multichannel multihead attention and multichannel linear layers to allow for parallel transformers effectively; aside from that it is the same as typical transformers. For memory, this makes use of the position-wise residual u-nets skip connection. As in the primer architecture, this makes use of squared relu for activation.

## References
- [1] Jansson et al., "Singing Voice Separation with Deep U-Net Convolutional Networks", https://ismir2017.smcnus.org/wp-content/uploads/2017/10/171_Paper.pdf
- [2] Takahashi et al., "Multi-scale Multi-band DenseNets for Audio Source Separation", https://arxiv.org/pdf/1706.09588.pdf
- [3] Takahashi et al., "MMDENSELSTM: AN EFFICIENT COMBINATION OF CONVOLUTIONAL AND RECURRENT NEURAL NETWORKS FOR AUDIO SOURCE SEPARATION", https://arxiv.org/pdf/1805.02410.pdf
- [4] Liutkus et al., "The 2016 Signal Separation Evaluation Campaign", Latent Variable Analysis and Signal Separation - 12th International Conference
- [5] Vaswani et al., "Attention Is All You Need", https://arxiv.org/pdf/1706.03762.pdf
- [6] So et al., "Primer: Searching for Efficient Transformers for Language Modeling", https://arxiv.org/pdf/2109.08668v2.pdf
- [7] Su et al., "RoFormer: Enhanced Transformer with Rotary Position Embedding", https://arxiv.org/abs/2104.09864
- [8] Henry et al., "Query-Key Normalization for Transformers", https://arxiv.org/pdf/2010.04245.pdf
- [9] Asiedu et all., "Decoder Denoising Pretraining for Semantic Segmentation", https://arxiv.org/abs/2205.11423
