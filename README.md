## Temporal Shift Module for Dynamic Indian Sign Language Recognition 

According to [mit official code](https://github.com/mit-han-lab/temporal-shift-module), 
we reduce and modify some codes for jester dataset.

### Prerequisites

* cuda toolkit 10.2.0
* Python 3.9
* PyTorch 1.11.0
* Opencv 3.5.5
* gxx 11.2.0
* numpy 1.21.2

### Data Preparation

The BharatDSL dataset is not open yet. 
The dataset has to be downloaded and then is accessed using the .csv files at location datas/BharatDSL/

### Train and Validate

`bash train.sh`

After total training epochs, you can get result.csv, 
that is the test result document, including video number and corresponding label.

### Reference

[paper links](https://arxiv.org/abs/1811.08383)
