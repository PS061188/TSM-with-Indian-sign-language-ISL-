def dataset():
    prefix = '{:05d}.png'
    file_categories = 'datas/BharatDSL/category.txt'
    file_imglist_train = 'datas/BharatDSL/BharatDSL_train.txt'
    file_imglist_val = 'datas/BharatDSL/BharatDSL_validation.csv'
    file_imglist_test = 'datas/BharatDSL/BharatDSL_test.csv'

    with open(file_categories) as f:
        lines = f.readlines()
    categories = [item.rstrip() for item in lines]
    n_class = len(categories)
    print('BharatDSL: {} classes'.format(n_class))

    return n_class, file_imglist_train, file_imglist_val, file_imglist_test, prefix
