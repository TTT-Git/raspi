# Circuit Playground Express Demo Code
# Adjust the pulseio 'board.PIN' if using something else
import pulseio
import board
import adafruit_irremote

from gpio import gpio
import settings

pulsein = pulseio.PulseIn(gpio[settings.gpio_irreceiver], maxlen=120, idle_state=True)
decoder = adafruit_irremote.GenericDecode()


while True:
    pulses = decoder.read_pulses(pulsein)
    print("Heard", len(pulses), "Pulses:", pulses)
    for pluse in pulses:
        t = round(pluse / 425,1)
        print(t, round(t))
    try:
        code = decoder.decode_bits(pulses)
        print("Decoded:", code)
    except adafruit_irremote.IRNECRepeatException:  # unusual short code!
        print("NEC repeat!")
    except adafruit_irremote.IRDecodeException as e:     # failed to decode
        print("Failed to decode: ", e.args)
    except Exception as error:
        print(error)

    print("----------------------------")



def decode_bits(pulses):
    """Decode the pulses into bits."""
    # pylint: disable=too-many-branches,too-many-statements

    # TODO The name pulses is redefined several times below, so we'll stash the
    # original in a separate variable for now. It might be worth refactoring to
    # avoid redefining pulses, for the sake of readability.
    input_pulses = tuple(pulses)
    pulses = list(pulses)  # Copy to avoid mutating input.

    # special exception for NEC repeat code!
    if (
        (len(pulses) == 3)
        and (8000 <= pulses[0] <= 10000)
        and (2000 <= pulses[1] <= 3000)
        and (450 <= pulses[2] <= 700)
    ):
        return NECRepeatIRMessage(input_pulses)

    if len(pulses) < 10:
        msg = UnparseableIRMessage(input_pulses, reason="Too short")
        raise FailedToDecode(msg)

    # Ignore any header (evens start at 1), and any trailer.
    if len(pulses) % 2 == 0:
        pulses_end = -1
    else:
        pulses_end = None

    evens = pulses[1:pulses_end:2]
    odds = pulses[2:pulses_end:2]

    # bin both halves
    even_bins = bin_data(evens)
    odd_bins = bin_data(odds)

    outliers = [b[0] for b in (even_bins + odd_bins) if b[1] == 1]
    even_bins = [b for b in even_bins if b[1] > 1]
    odd_bins = [b for b in odd_bins if b[1] > 1]

    if not even_bins or not odd_bins:
        msg = UnparseableIRMessage(input_pulses, reason="Not enough data")
        raise FailedToDecode(msg)

    if len(even_bins) == 1:
        pulses = odds
        pulse_bins = odd_bins
    elif len(odd_bins) == 1:
        pulses = evens
        pulse_bins = even_bins
    else:
        msg = UnparseableIRMessage(input_pulses, reason="Both even/odd pulses differ")
        raise FailedToDecode(msg)

    if len(pulse_bins) == 1:
        msg = UnparseableIRMessage(input_pulses, reason="Pulses do not differ")
        raise FailedToDecode(msg)
    if len(pulse_bins) > 2:
        msg = UnparseableIRMessage(input_pulses, reason="Only mark & space handled")
        raise FailedToDecode(msg)

    mark = min(pulse_bins[0][0], pulse_bins[1][0])
    space = max(pulse_bins[0][0], pulse_bins[1][0])

    if outliers:
        # skip outliers
        pulses = [
            p for p in pulses if not (outliers[0] * 0.75) <= p <= (outliers[0] * 1.25)
        ]
    # convert marks/spaces to 0 and 1
    for i, pulse_length in enumerate(pulses):
        if (space * 0.75) <= pulse_length <= (space * 1.25):
            pulses[i] = False
        elif (mark * 0.75) <= pulse_length <= (mark * 1.25):
            pulses[i] = True
        else:
            msg = UnparseableIRMessage(input_pulses, reason="Pulses outside mark/space")
            raise FailedToDecode(msg)

    # convert bits to bytes!
    output = [0] * ((len(pulses) + 7) // 8)
    for i, pulse_length in enumerate(pulses):
        output[i // 8] = output[i // 8] << 1
        if pulse_length:
            output[i // 8] |= 1
    return IRMessage(tuple(input_pulses), code=tuple(output))


