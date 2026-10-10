"""Source-frame-bound editorial spotlights for the English presentation cut.

These are assistant-drawn visible-body mattes, not model segmentation, tracking,
measured court positions, or reconstructed limbs. They apply only to three held
1920 x 1080 source frames. Occluded feet are deliberately not given floor rings.
Call ``apply_focus`` after grading the camera image and before adding UI layers.
The existing camera-to-board transition and shot duration remain unchanged.
"""
from functools import lru_cache

import cv2
import numpy as np

SOURCE_SHA256 = "f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91"
SOURCE_FRAMES = {"T1": 240, "T3": 480, "T2": 719}
CANVAS = (1080, 1920)

# BGR light colors: Christie amber, Powell cyan, Smith coral. Polygons describe
# the visible image, not a complete body behind another player or broadcast UI.
_FOCUS = {
    "T1": (
        {"player": "Jabari Smith Jr.", "color": (106, 104, 255),
         "polygons": (((925, 612), (949, 611), (959, 625), (957, 642),
                       (979, 653), (1016, 654), (1022, 666), (978, 675),
                       (946, 676), (958, 700), (979, 729), (1003, 744),
                       (994, 756), (968, 742), (937, 713), (930, 700),
                       (909, 754), (915, 774), (910, 797), (891, 838),
                       (910, 870), (907, 887), (887, 883), (867, 864),
                       (850, 883), (853, 896), (843, 902), (813, 891),
                       (809, 881), (820, 863), (841, 826), (849, 798),
                       (831, 764), (825, 738), (831, 697), (856, 662),
                       (902, 638), (922, 629)),),
         "foot": (838, 896), "ring_axes": (42, 11)},
        {"player": "Max Christie", "color": (68, 169, 255),
         "polygons": (((1038, 638), (1063, 632), (1073, 644),
                       (1073, 660), (1062, 677), (1081, 699),
                       (1094, 704), (1101, 682), (1107, 672),
                       (1120, 673), (1132, 690), (1131, 711),
                       (1114, 730), (1092, 744), (1069, 744),
                       (1067, 769), (1089, 800), (1093, 819),
                       (1075, 850), (1088, 878), (1081, 893),
                       (1062, 886), (1055, 873), (1054, 901),
                       (1051, 922), (1065, 939), (1066, 951),
                       (1056, 956), (1034, 950), (1029, 935),
                       (1033, 914), (1027, 869), (1013, 841),
                       (996, 810), (988, 777), (993, 739),
                       (1008, 710), (1022, 683), (1030, 668)),),
         "foot": (1048, 951), "ring_axes": (44, 11)},
    ),
    "T3": (
        {"player": "Dwight Powell", "color": (245, 211, 61),
         "polygons": (((1138, 537), (1163, 533), (1175, 546),
                       (1174, 565), (1169, 578), (1185, 584),
                       (1194, 609), (1195, 665), (1201, 699),
                       (1211, 718), (1207, 733), (1197, 731),
                       (1184, 703), (1176, 672), (1166, 701),
                       (1170, 748), (1163, 794), (1155, 817),
                       (1137, 826), (1134, 788), (1143, 746),
                       (1134, 713), (1116, 709), (1111, 739),
                       (1097, 763), (1083, 759), (1083, 740),
                       (1090, 709), (1098, 678), (1103, 647),
                       (1106, 602), (1120, 582), (1139, 575),
                       (1130, 556)),),
         # The foreground referee overlaps the lower body: no invented foot ring.
         "exclude": (((1094, 773), (1110, 765), (1128, 768), (1140, 784),
                      (1141, 809), (1151, 821), (1140, 836), (1088, 831),
                      (1085, 805)),),
         "foot": None},
        {"player": "Max Christie", "color": (68, 169, 255),
         "polygons": (((1560, 658), (1582, 660), (1597, 673),
                       (1595, 691), (1589, 707), (1613, 718),
                       (1626, 744), (1624, 791), (1631, 816),
                       (1621, 850), (1608, 875), (1545, 875),
                       (1548, 847), (1560, 813), (1568, 784),
                       (1534, 800), (1501, 818), (1468, 829),
                       (1456, 823), (1458, 816), (1490, 804),
                       (1520, 789), (1553, 762), (1558, 738),
                       (1550, 715), (1538, 698), (1536, 682),
                       (1545, 666)),),
         # Source score bug covers the lower body at y=877; no extrapolation.
         "foot": None},
    ),
    "T2": (
        {"player": "Jabari Smith Jr.", "color": (106, 104, 255),
         "polygons": (((1160, 630), (1180, 629), (1189, 641),
                       (1188, 657), (1203, 668), (1228, 688),
                       (1245, 722), (1259, 748), (1261, 777),
                       (1273, 806), (1303, 830), (1326, 851),
                       (1347, 866), (1354, 881), (1348, 890),
                       (1335, 894), (1327, 879), (1305, 866),
                       (1270, 847), (1240, 824), (1225, 798),
                       (1210, 772), (1190, 756), (1166, 723),
                       (1152, 707), (1130, 697), (1102, 681),
                       (1092, 666), (1089, 643), (1096, 637),
                       (1103, 651), (1107, 664), (1131, 674),
                       (1158, 669), (1153, 652)),),
         "foot": (1337, 885), "ring_axes": (39, 10)},
        {"player": "Max Christie", "color": (68, 169, 255),
         "polygons": (((1121, 687), (1142, 685), (1154, 695),
                       (1157, 709), (1179, 712), (1194, 731),
                       (1205, 759), (1221, 780), (1227, 801),
                       (1223, 827), (1211, 848), (1215, 860),
                       (1242, 876), (1239, 884), (1217, 880),
                       (1201, 876), (1167, 863),
                       (1144, 848), (1127, 844), (1119, 834),
                       (1126, 822), (1133, 791), (1133, 762),
                       (1117, 755), (1098, 763), (1093, 753),
                       (1117, 741), (1129, 729), (1115, 713),
                       (1110, 703)),),
         # Foreground spectators and referee hide the feet in this source frame.
         "foot": None},
    ),
}


def _smooth(value):
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3 - 2 * value)


@lru_cache(maxsize=3)
def _fields(name):
    """Cache modest local mattes; never generate geometry on moving frames."""
    players = _FOCUS[name]
    coordinates = np.concatenate([np.asarray(polygon) for player in players
                                  for polygon in player["polygons"]])
    x0, y0 = np.maximum(coordinates.min(axis=0) - (70, 48), (0, 0))
    x1, y1 = np.minimum(coordinates.max(axis=0) + (70, 48), (1920, 1080))
    shape = (int(y1 - y0), int(x1 - x0))
    origin = np.array((x0, y0))
    masks = []
    for player in players:
        mask = np.zeros(shape, np.uint8)
        for polygon in player["polygons"]:
            points = np.asarray(polygon, np.int32) - origin
            cv2.fillPoly(mask, [points], 255, lineType=cv2.LINE_AA)
        for polygon in player.get("exclude", ()):
            points = np.asarray(polygon, np.int32) - origin
            cv2.fillPoly(mask, [points], 0, lineType=cv2.LINE_AA)
        masks.append(mask)
    # The foreground ball handler must never inherit the defender's light.
    if len(masks) == 2:
        masks[0] = cv2.subtract(masks[0], masks[1])
    inside = np.zeros(shape, np.float32)
    light = np.zeros((*shape, 3), np.float32)
    for player, mask in zip(players, masks):
        matte = mask.astype(np.float32) / 255
        soft = cv2.GaussianBlur(matte, (0, 0), 12)
        feather = cv2.GaussianBlur(matte, (0, 0), 2.5)
        inside = np.maximum(inside, np.maximum(feather, soft * .68))
        border = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT,
                                 np.ones((3, 3), np.uint8)).astype(np.float32) / 255
        rim = cv2.GaussianBlur(border, (0, 0), 1.2) * .36
        rim += cv2.GaussianBlur(border, (0, 0), 7) * 1.15
        color = np.asarray(player["color"], np.float32)
        light += rim[..., None] * color
        if player["foot"]:
            floor = np.zeros(shape, np.uint8)
            center = tuple(np.asarray(player["foot"]) - origin)
            cv2.ellipse(floor, center, player["ring_axes"], -5, 0, 360,
                        255, 2, cv2.LINE_AA)
            floor_soft = cv2.GaussianBlur(floor.astype(np.float32) / 255,
                                          (0, 0), 3.8)
            light += floor_soft[..., None] * color * .65
    return int(x0), int(y0), int(x1), int(y1), inside, light


def apply_focus(base, name, t, morph, release):
    """Return a lit BGR camera image, fading out before the schematic board.

    ``base`` must be the graded 1080p source freeze for ``SOURCE_FRAMES[name]``.
    This function neither changes time nor draws text. At t=0, full board, and
    the returning-video release it is exactly an identity operation.
    """
    if name not in _FOCUS:
        return base
    # Time fade prevents reappearance when morph decreases at the end of a hold.
    envelope = _smooth(t / .30) * (1 - _smooth((t - 1.08) / .78))
    envelope *= (1 - _smooth(morph)) * (1 - float(np.clip(release, 0, 1)))
    if envelope < .0001:
        return base
    if base.shape[:2] != CANVAS or base.dtype != np.uint8:
        raise ValueError("Editorial spotlights require the bound 1920x1080 uint8 source frame")
    # A slow, shallow breath keeps the held image alive without flicker.
    envelope *= .97 + .03 * np.sin(np.pi * t / 1.15)
    x0, y0, x1, y1, inside, light = _fields(name)
    amount = .22 * envelope
    result = base.astype(np.float32) * (1 - amount)
    roi = result[y0:y1, x0:x1]
    roi += base[y0:y1, x0:x1].astype(np.float32) * inside[..., None] * (amount + .10 * envelope)
    roi += light * envelope
    return np.clip(result, 0, 255).astype(np.uint8)
