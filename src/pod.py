# Copyright (C) 2026 Petros Baloglou, University of Macedonia

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from datetime import datetime

def parse_log_line(line: str) -> tuple[float, str]:
    stamp, text = line.split(' ', maxsplit=1)
    if stamp.endswith("Z"):
        offset = "+00:00"
        fraction = stamp[19:-1]
    else:
        offset = stamp[-6:]
        fraction = stamp[19:-6]
    return datetime.fromisoformat(stamp[:19] + offset).timestamp() + float("0" + fraction), text