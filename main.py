import os
import time
import torch.optim
import torch.nn as nn
import torch.backends.cudnn as cudnn
from datetime import datetime
from torch.utils.tensorboard import SummaryWriter
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix

from datas.dataset import TSNDataSet
from ops.models import TSN
from ops.transforms import *
from options import parser
from datas import dataset_config
from ops.utils import AverageMeter, accuracy, save_checkpoint, adjust_learning_rate, check_rootfolders

best_prec1 = 0


def main():
    # settings
    global args, best_prec1
    args = parser.parse_args()
    n_class, args.train_list, args.val_list, args.test_list, prefix = dataset_config.dataset()
    full_arch_name = args.arch
    if args.shift:
        full_arch_name += '_shift{}'.format(args.shift_div)
    args.store_name = '_'.join(
        ['tsm', full_arch_name, 'segment%d' % args.num_segments])
    print('storing name: ' + args.store_name)
    check_rootfolders(args.root_log, args.root_model, args.store_name)

    # tsn model added temporal shift module
    model = TSN(n_class, args.num_segments,
                base_model=args.arch,
                dropout=args.dropout,
                partial_bn=not args.no_partialbn,
                is_shift=args.shift, shift_div=args.shift_div)

    # preprocessing for input
    crop_size = model.crop_size
    scale_size = model.scale_size
    input_mean = model.input_mean
    input_std = model.input_std
    policies = model.get_optim_policies()
    train_augmentation = model.get_augmentation(flip=False)

    # optimizer
    optimizer = torch.optim.SGD(policies, args.lr, momentum=args.momentum, weight_decay=args.weight_decay)

    # cuda and cudnn
    try:
        model = nn.DataParallel(model).cuda()
    except:
        model = model.cuda()
    cudnn.benchmark = True

    # data loader
    normalize = GroupNormalize(input_mean, input_std)
    train_loader = torch.utils.data.DataLoader(
        TSNDataSet(args.train_list,
                   num_segments=args.num_segments,
                   transform=torchvision.transforms.Compose([
                       train_augmentation,
                       Stack(roll=False),
                       ToTorchFormatTensor(div=True),
                       normalize])),
        batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, pin_memory=False, drop_last=True)

    val_loader = torch.utils.data.DataLoader(
        TSNDataSet(args.val_list,
                   num_segments=args.num_segments,
                   random_shift=False,
                   transform=torchvision.transforms.Compose([
                       GroupScale(int(scale_size)),
                       GroupCenterCrop(crop_size),
                       Stack(roll=False),
                       ToTorchFormatTensor(div=True),
                       normalize])),
        batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=False)

    test_loader = torch.utils.data.DataLoader(
        TSNDataSet(args.test_list,
                   num_segments=args.num_segments,
                   random_shift=False,
                   test_mode=True,
                   transform=torchvision.transforms.Compose([
                       GroupScale(int(scale_size)),
                       GroupCenterCrop(crop_size),
                       Stack(roll=False),
                       ToTorchFormatTensor(div=True),
                       normalize])),
        batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=False)

    # loss function
    criterion = nn.CrossEntropyLoss().cuda()
    for group in policies:
        print(('group: {} has {} params, lr_mult: {}, decay_mult: {}'.format(
            group['name'], len(group['params']), group['lr_mult'], group['decay_mult'])))

    # tensorboard
    time_stamp = "{0:%Y-%m-%dT%H-%M-%S/}".format(datetime.now())

    # train
    if args.mode == 'train':
        directory = os.path.join(args.root_log, args.store_name, time_stamp)
        if not os.path.exists(directory):
            os.makedirs(directory)
        log_training = open(os.path.join(args.root_log, args.store_name, time_stamp, 'log.csv'), 'w')
        tf_writer = SummaryWriter('{}/{}/'.format(args.root_log, args.store_name) + time_stamp)
        for epoch in range(args.start_epoch, args.epochs):
            adjust_learning_rate(optimizer, epoch, args.lr_steps, args.lr, args.weight_decay)
            train(train_loader, model, criterion, optimizer, epoch, log_training, tf_writer)

            # evaluate on validation set
            if (epoch + 1) % args.eval_freq == 0:
                prec1 = validate(val_loader, model, criterion, epoch, log_training, tf_writer)

                # remember best precision and save checkpoint
                is_best = prec1 >= best_prec1
                best_prec1 = max(prec1, best_prec1)
                output_best = 'Best Prec@1: %.2f\n' % (best_prec1)
                print(output_best)
                log_training.write(output_best + '\n')
                log_training.flush()

                save_checkpoint({
                    'epoch': epoch + 1,
                    'arch': args.arch,
                    'state_dict': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'best_prec1': best_prec1,
                }, is_best, args.root_model, args.store_name)
                tf_writer.close()

    # test
    checkpoint = '%s/%s/ckpt.best.pth.tar' % (args.root_model, args.store_name)
    test(test_loader, model, checkpoint, time_stamp)


def train(train_loader, model, criterion, optimizer, epoch, log, tf_writer):
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    if args.no_partialbn:
        try:
            model.module.partialBN(False)
        except:
            model.partialBN(False)
    else:
        try:
            model.module.partialBN(True)
        except:
            model.partialBN(True)
    model.train()

    end = time.time()
    for idx, (input, target) in enumerate(train_loader):
        data_time.update(time.time() - end)
        input, target = input.cuda(), target.cuda()
        output = model(input)
        loss = criterion(output, target)

        # accuracy and loss
        prec1, = accuracy(output.data, target, topk=(1,))
        losses.update(loss.item(), input.size(0))
        top1.update(prec1.item(), input.size(0))

        # gradient and optimizer
        loss.backward()
        if (idx + 1) % args.update_weight == 0:
            optimizer.step()
            optimizer.zero_grad()

        # time
        batch_time.update(time.time() - end)
        end = time.time()
        if (idx + 1) % args.print_freq == 0:
            output = ('Train: epoch-{0} ({1}/{2})\t'
                      'batch_time {batch_time.avg:.2f}\t\t'
                      'data_time {data_time.avg:.2f}\t\t'
                      'loss {loss.avg:.3f}\t'
                      'prec@1 {top1.avg:.2f}\t'.format(
                epoch, idx + 1, len(train_loader), batch_time=batch_time,
                data_time=data_time, loss=losses, top1=top1))
            batch_time.reset()
            data_time.reset()
            losses.reset()
            top1.reset()
            print(output)
            log.write(output + '\n')
            log.flush()

    tf_writer.add_scalar('loss/train', losses.avg, epoch)
    tf_writer.add_scalar('acc/train_top1', top1.avg, epoch)
    tf_writer.add_scalar('lr', optimizer.param_groups[-1]['lr'], epoch)


def validate(val_loader, model, criterion, epoch, log, tf_writer):
    losses = AverageMeter()
    top1 = AverageMeter()
    model.eval()
    with torch.no_grad():
        for input, target in val_loader:
            input, target = input.cuda(), target.cuda()
            output = model(input)
            loss = criterion(output, target)

            # accuracy and loss
            prec1, = accuracy(output.data, target, topk=(1,))
            losses.update(loss.item(), input.size(0))
            top1.update(prec1.item(), input.size(0))

    output = ('Validate: Prec@1 {top1.avg:.2f}  Loss {loss.avg:.3f}'.format(top1=top1, loss=losses))
    print(output)
    log.write(output + '\n')
    log.flush()
    tf_writer.add_scalar('loss/val', losses.avg, epoch)
    tf_writer.add_scalar('acc/val_top1', top1.avg, epoch)

    return top1.avg


def test(test_loader, model, checkpoint, time_stamp):
    model.load_state_dict(torch.load(checkpoint)['state_dict'])
    model.eval()
    labels = []
    with torch.no_grad():
        for input in test_loader:
            input = input.cuda()
            output = model(input)
            pred = output.argmax(dim=1).cpu().numpy().tolist()
            labels.extend(pred)

    with open('datas/BharatDSL/BharatDSL_test.csv') as f:
        videos = f.readlines()
    with open('datas/BharatDSL/category.txt') as f:
        categories = f.readlines()
    assert len(videos) == len(labels)
    result = []
    for idx in range(len(labels)):
        v = videos[idx].strip()
        v = v.split(',')
        result.append(os.path.join(v[1]) + ';' + categories[labels[idx]].rstrip())
    with open(os.path.join(args.root_log, args.store_name, time_stamp, 'result.csv'), 'w') as f:
        f.write('\n'.join(result))
    count = 0
    y_pred = []
    y_true = []
    for i in result:
        i = i.split(';')
        actual = i[1]
        truth = i[0]
        y_pred.append(actual)
        y_true.append(truth)
        if actual == truth:
           count += 1
    accuracy = count/len(labels)
    accuracy = accuracy * 100
    print('Accuracy = ', accuracy)
    cf_matrix = confusion_matrix(y_true, y_pred, labels=["Absent", "Accuse", "Always", "Appear", "Beautiful", "Borrow", "Can", "Cheap", "Come", "Decrease", "Demand", "Easy", "Expensive", "Fail", "False", "Far", "Fast", "Forget", "High", "Hot", "Import", "Increase", "Leave", "Less", "Liquid", "Low", "Lucky", "Me", "More", "Reject", "Right", "Short", "Slow", "Thin", "True", "Ugly", "Unlucky", "Weak", "What", "When", "Why", "Wrong", "You"])
    print(cf_matrix)
    #ax = sns.heatmap(cf_matrix, annot=True, cmap='Blues')
    #ax.set_title('Confusion Matrix with labels\n\n');
    #ax.set_xlabel('\nPredicted Values')
    #ax.set_ylabel('Actual Values ');

    ## Ticket labels - List must be in alphabetical order
    #ax.xaxis.set_ticklabels(["Absent", "Accuse", "Always", "Appear", "Beautiful", "Borrow", "Can", "Cheap", "Come", "Decrease", "Demand", "Easy", "Expensive", "Fail", "False", "Far", "Fast", "Forget", "High", "Hot", "Import", "Increase", "Leave", "Less", "Liquid", "Low", "Lucky", "Me", "More", "Reject", "Right", "Short", "Slow", "Thin", "True", "Ugly", "Unlucky", "Weak", "What", "When", "Why", "Wrong", "You"])
    #ax.yaxis.set_ticklabels(["Absent", "Accuse", "Always", "Appear", "Beautiful", "Borrow", "Can", "Cheap", "Come", "Decrease", "Demand", "Easy", "Expensive", "Fail", "False", "Far", "Fast", "Forget", "High", "Hot", "Import", "Increase", "Leave", "Less", "Liquid", "Low", "Lucky", "Me", "More", "Reject", "Right", "Short", "Slow", "Thin", "True", "Ugly", "Unlucky", "Weak", "What", "When", "Why", "Wrong", "You"])

    ## Display the visualization of the Confusion Matrix.
    #plt.show()
    #plt.savefig('confusion_matrix.png')

if __name__ == '__main__':
    main()
