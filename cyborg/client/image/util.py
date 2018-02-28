import hashlib
import os
from oslo_utils import units

# define the NAME and ID with lower case.
VENDOR_NAME_ID_MAPS = {"intel": "0x8086"}
VENDOR_ID_NAME_MAPS = dict(map(reversed, VENDOR_NAME_ID_MAPS.items()))
FGPA_IMGAGE_PATH = "/tmp/cyborg/image/fpgas"
TEST_FILE = "/home/ubuntu/api_tests/token.json"

def get_vendors():
    # vs get from drivers, can be a parameters.
    vs = ["0x8086"]
    ret = set()
    for v_id in vs:
        if v_id.lower() in VENDOR_ID_NAME_MAPS.keys():
            ret.add(v_id.upper())
        v_name = VENDOR_ID_NAME_MAPS.get(v_id.lower(), v_id)
        ret.add(v_name.upper())
    return ret


def vendor_id_to_name(v_id):
    if not v_id:
        return v_id
    vendor = VENDOR_ID_NAME_MAPS.get(v_id.lower(), v_id)
    return vendor.upper()


def vendor_name_to_id(name):
    if not name:
        return name
    v_id = VENDOR_NAME_ID_MAPS.get(name.lower(), name)
    return v_id.upper()


def gen_traits_and_resource_type(images):
    infos = {}
    # CUSTOM_FPGA_VENDOR_TYPE
    vendors = get_vendors()
    for uuid, img in images["images"].items():
        res_types = ["CUSTOM", "FPGA"]
        traits = set()
        vendor = "unknow"
        tags = set([x.upper() for x in img["tags"]])
        v_name = vendor_id_to_name(img.get("vendor"))
        if v_name and v_name in vendors:
            vendor = v_name
            traits.update(tags)
            res_types.append(v_name)
        elif tags & vendors:
            traits.update(tags)
            v_name = vendor_id_to_name(list(tags & vendors)[0])
            vendor = v_name
            res_types.append(v_name)

        v_info = infos.setdefault(vendor,
            {"function": set(), "traits": set(), "resource": res_types})
        fpga_type = img.get("type")
        if fpga_type:
            traits.add(fpga_type.upper())
            v_info["function"].add(fpga_type.upper())
        infos[vendor]["traits"] = infos[vendor]["traits"] | traits

    return infos


def get_image_uuid_by_match_requirement(images, resource_name, traits):
    if resource_name.count("_") < 3:
        return
    infos = resource_name.split("_")[2:]
    vend, hw_type = infos[:2]
    vend = vendor_id_to_name(vend)
    typ = hw_type.upper()
    infos = images["summary"].get(vend)
    if not infos:
        return
    functions = set(traits) & infos.get("function", set())
    if len(functions) != 1:
        print("Get function %s from requirement, "
              "Unknow which is the exact one." % functions)
        return
    function = functions.pop()
    # img_info = dict(zip(["vendor", "type"], infos))
    for k, img in images["images"].items():
        i_vendor = vendor_id_to_name(img.get("vendor"))
        i_typ = img.get("type")
        if function == i_typ.upper():
            if vend == i_vendor:
                return k
            v_id = vendor_name_to_id(vend)
            tags = set([x.upper() for x in img["tags"]])
            if v_id in tags or vend in tags:
                return k



def hash_for_file(path, algorithm=hashlib.algorithms[0],
                  block_size= 64 * units.Mi, human_readable=True):
    """
    Block size directly depends on the block size of your filesystem
    to avoid performances issues
    NTFS has blocks of 4096 octets by default.

    Linux Ext4 block size
    sudo tune2fs -l /dev/sda5 | grep -i 'block size'
    > Block size:               4096

    Input:
        path: a path
        algorithm: an algorithm in hashlib.algorithms
                   ATM: ('md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512')
        block_size: a multiple of 128 corresponding to the block size of your
                    filesystem. Here keep the same value of glance by default.
        human_readable: switch between digest() or hexdigest() output,
                        default hexdigest()
    Output:
        hash
    """
    if algorithm not in hashlib.algorithms:
        raise NameError('The algorithm "{algorithm}" you specified is '
                        'not a member of "hashlib.algorithms"'
                        ''.format(algorithm=algorithm))

    # According to hashlib documentation using new()
    # will be slower then calling using named
    # constructors, ex.: hashlib.md5()
    hash_algo = hashlib.new(algorithm)

    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block_size), b''):
             hash_algo.update(chunk)
    if human_readable:
        file_hash = hash_algo.hexdigest()
    else:
        file_hash = hash_algo.digest()
    return file_hash


def download_image_check(uuid, md5, path=FGPA_IMGAGE_PATH):
    image = os.path.join(path, uuid)
    if not os.path.lexists(image):
        raise Exception("Image path is not exist.")
    image_md5 = hash_for_file(image)
    if md5 != image_md5:
        raise Exception("Download an incomplete image.")
    md5_file = image + "_md5"
    with open(md5_file, 'w') as f:
        f.write(image_md5)
    return True
