import os

if __name__ == '__main__':
    dataset = 'datas/BharatDSL/BharatDSL'
    dataset_name = 'BharatDSL'
    with open('%s_labels.csv' % dataset) as f:
        lines = f.readlines()
    categories = []
    for line in lines:
        line = line.rstrip()
        categories.append(line)
    categories = sorted(categories)
    with open('datas/BharatDSL/category.txt', 'w') as f:
        f.write('\n'.join(categories))

    dict_categories = {}
    for i, category in enumerate(categories):
        dict_categories[category] = i

    # train and validate dataset
    files_input = ['%s_validation.csv' % dataset, '%s_train.csv' % dataset]
    files_output = ['datas/BharatDSL/val_videofolder.txt', 'datas/BharatDSL/train_videofolder.txt']
    for (filename_input, filename_output) in zip(files_input, files_output):
        sets = filename_input.split('_')
        sets = sets[1].split('.')
        set_name = sets[0]
        with open(filename_input) as f:
            lines = f.readlines()
        folders = []
        folders_new = []
        idx_categories = []
        for line in lines:
            line = line.rstrip()
            items = line.split(';')
            folders.append(items[1])
            folders_new.append(items[0])
            idx_categories.append(dict_categories[items[1]])
        output = []
        for i in range(len(folders)):
            curFolder = folders[i]
            curIDX = idx_categories[i]
            dir_files = os.listdir(os.path.join('datas/BharatDSL/BharatDSL_dataset/', set_name, curFolder))
            output.append('%s %s %d %d' % ('datas/BharatDSL/BharatDSL_dataset/' + set_name, curFolder, len(dir_files), curIDX))
            print('%d/%d' % (i, len(folders)))
        with open(filename_output, 'w') as f:
            f.write('\n'.join(output))

    # test dataset
    with open('datas/BharatDSL/BharatDSL_test.csv') as f:
        lines = f.readlines()
    folders = []
    for line in lines:
        line = line.rstrip()
        items = line.split(';')
        folders.append(items[1])
    output = []
    for i in range(len(folders)):
        curFolder = folders[i]
        dir_files = os.listdir(os.path.join('datas/BharatDSL/BharatDSL_dataset/', 'test', curFolder))
        output.append('%s %s %d' % ('datas/BharatDSL/BharatDSL_dataset/' + 'test', curFolder, len(dir_files)))
        print('%d/%d' % (i, len(folders)))
    with open('datas/BharatDSL/test_videofolder.txt', 'w') as f:
        f.write('\n'.join(output))
