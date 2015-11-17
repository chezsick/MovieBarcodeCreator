#!/usr/bin/env python3

import os
import ast
import queue
import shutil
import argparse
import threading
import subprocess
from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument('filename', type=str, help='movie filename')
parser.add_argument('-fc', '--framecolors', action='store_true',
                    help='A frame_colors.txt file exists in the movies directory.')
parser.add_argument('-bw', '--barwidth', type=int, 
                    help='Set the width of the bars in the barcode. Default is 5px.')
parser.add_argument('-ht', '--height', type=int,
                    help='Set the height of the barcode. Default is 1200px.')
parser.add_argument('-w', '--width', type=int,
                    help='Set the final width of the barcode. Default is 1920px.')
parser.add_argument('-nd', '--nodelete', action='store_true',
                    help='Won\'t delete the movie frames after done executing.')
parser.add_argument('-nf', '--noframes', action='store_true',
                    help='Won\'t create the frames. Must already have them in a directory called frames.')
parser.add_argument('-fr', '--framerate', type=str,
                    help='Set the framerate for breaking the movie into frames. Default is 1/24.')
parser.add_argument('-t', '--threads', type=int,
                    help='Number of threads to be spawned when finding frame colors. Default is 8.')
args = parser.parse_args()


def create_movie_frames(infile):
    os.chdir('./frames')

    framerate = args.framerate if args.framerate else '1/24'
    ffmpeg_args = ['ffmpeg', '-threads', '0', '-i', '../' + infile, '-r', framerate,
                   '-f', 'image2', 'image-%07d.png']

    output = open('ffmpeg_log.txt', 'w')

    print('Creating frames (this might take a while)...')
    subprocess.call(ffmpeg_args, stderr=output, stdout=subprocess.PIPE)

    output.close()


def find_frame_bar_color(infile, last_col=None):
    img = Image.open(infile)
    result = img.convert('P', palette=Image.ADAPTIVE)
    result.putalpha(0)
    colors = result.getcolors()

    if last_col == colors[0][1]:
        return last_col

    return colors[0][1]


def get_image_colors(thread_id, q, images):
    colors = []
    for img in images:
        colors.append(find_frame_bar_color(img))

    q.put((thread_id, colors))


def distribute_frame_lists(n):
    img_list = [img for img in os.listdir(os.getcwd()) if img.endswith('.png')]
    slice_size = len(img_list) // n
    remainder = len(img_list) % n
    result = []
    iterater = iter(img_list)

    for i in range(n):
        result.append([])
        for j in range(slice_size):
            result[i].append(next(iterater))
        if remainder:
            result[i].append(next(iterater))
            remainder -= 1

    return result


def spawn_threads():
    # change directories if it already isn't in frames
    if not '/frames' in os.getcwd():
        os.chdir('frames')

    q = queue.Queue()
    num_threads = args.threads if args.threads else 8

    # get a distributed list of images for the threads
    images = distribute_frame_lists(num_threads)

    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=get_image_colors, args=(i, q, images[i]))
        threads.append(thread)

    print('Generating frame colors...')
    for thread in threads:
        thread.daemon = True
        thread.start()

    thread_results = [None] * num_threads
    for i in range(num_threads):
        result = q.get()
        thread_results[result[0]] = result[1]

    # return to the original directory
    os.chdir('..')

    return [item for sublist in thread_results for item in sublist]


def create_barcode(colors, bar_width, height, width):
    barcode_width = len(colors) * bar_width
    bc = Image.new('RGB', (barcode_width, height))
    draw = ImageDraw.Draw(bc)

    posx = 0
    print('Creating barcode...')
    for color in colors:
        draw.rectangle([posx, 0, posx + bar_width, height], fill=color)
        posx += bar_width

    del draw

    bc = bc.resize((width, height), Image.ANTIALIAS)
    bc.save('barcode.png', 'PNG')


def main():
    try:
        # attempt to create the directory structure if it doesn't exist
        os.mkdir('frames')
    except FileExistsError:
        pass

    fname = args.filename
    bar_width = args.barwidth if args.barwidth else 5
    height = args.height if args.height else 1200
    width = args.width if args.width else 1920

    if not args.noframes:
        create_movie_frames(fname)

    if not args.framecolors:
        colors = spawn_threads()

        with open('frame_colors.txt', 'w') as f:
            f.write('\n'.join('(%i, %i, %i, %i)' % x for x in colors))
    else:
        with open('frame_colors.txt', 'r') as f:
            colors = [ast.literal_eval(line) for line in f]

    create_barcode(colors, bar_width, height, width)

    if not args.nodelete:
        print('Cleaning up...')
        shutil.rmtree('frames')


if __name__ == '__main__':
    main()