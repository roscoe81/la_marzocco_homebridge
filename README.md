# lamarz_homebridge
This project interfaces a La Marzocco Linea Mini R Coffee Machine to [Homebridge](https://github.com/homebridge/homebridge) via mqtt, so that the machine can be controlled and monitored by the Apple Home app. It provides the capability to use Siri for controlling:

- Machine Power
- Boiler Temperature Levels
- Steam Power
- Steam Levels
- Brew By Weight dose and weight settings
- Backflush Initiation

It's based on the [La Marzocco Python Client](https://github.com/zweckj/pylamarzocco), modified to address some Brew By Weight issues and to use local time [here]( https://github.com/roscoe81/pylamarzocco). It uses the [HomeBridge MQTT Plug In](https://github.com/cflurin/homebridge-mqtt) to provide the interface with Homebridge.

## Setting Up

Populate the following fields with your own data.

```sh
SERIAL = "<Your La Marzocco Machine's Serial Number"
USERNAME = "<Your La Marzocco Account User Name>"
PASSWORD = "<Your La Marzocco Account Password>"
MQTT_BROKER_IP_ADDRESS = "<Your mqtt Broker IP Address>"
```

Configure the [HomeBridge MQTT Plug In](https://github.com/cflurin/homebridge-mqtt) using [Node-RED](https://nodered.org)

Each of the Apple Home controls are set up on the Homebridge MQTT Plugin using the Node_RED with the topic ```sh Óhomebridge/to/addÓ ``` with each of the following payloads:

```sh
{
    "name": "Coffee Power",
    "service_name": "Coffee Power",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Boiler Ready",
    "service_name": "Coffee Boiler Ready",
    "service": "MotionSensor"
}
```

```sh
{
    "name": "Coffee Temp",
    "service_name": "Coffee Temp",
    "service": "Thermostat",
    "TargetTemperature": {
        "minValue": 80,
        "maxValue": 99,
        "minStep": 0.1
    },
    "CurrentTemperature": {
        "minValue": 80,
        "maxValue": 99,
        "minStep": 0.1
    },
    "TargetHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    },
    "CurrentHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    }
}
```

```sh
{
    "name": "Coffee Steam",
    "service_name": "Coffee Steam",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Steam Ready",
    "service_name": "Coffee Steam Ready",
    "service": "MotionSensor"
}
```

```sh
{
    "name": "Coffee Steam 1",
    "service_name": "Coffee Steam 1",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Steam 2",
    "service_name": "Coffee Steam 2",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Steam 3",
    "service_name": "Coffee Steam 3",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Dose 1",
    "service_name": "Coffee Dose 1",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Dose 2",
    "service_name": "Coffee Dose 2",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Continuous",
    "service_name": "Coffee Continuous",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee BBW 1",
    "service_name": "Coffee BBW 1",
    "service": "Thermostat",
    "TargetTemperature": {
        "minValue": 14,
        "maxValue": 42,
        "minStep": 0.1
    },
    "CurrentTemperature": {
        "minValue": 14,
        "maxValue": 42,
        "minStep": 0.1
    },
    "TargetHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    },
    "CurrentHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    }
}
```

```sh
{
    "name": "Coffee BBW 2",
    "service_name": "Coffee BBW 2",
    "service": "Thermostat",
    "TargetTemperature": {
        "minValue": 14,
        "maxValue": 42,
        "minStep": 0.1
    },
    "CurrentTemperature": {
        "minValue": 14,
        "maxValue": 42,
        "minStep": 0.1
    },
    "TargetHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    },
    "CurrentHeatingCoolingState": {
        "minValue": 0,
        "maxValue": 1
    }
}
```

```sh
{
    "name": "Coffee Backflush",
    "service_name": "Coffee Backflush",
    "service": "Switch"
}
```

```sh
{
    "name": "Coffee Action Backflush",
    "service_name": "Coffee Action Backflush",
    "service": "MotionSensor"
}
```

## Limitations
There are limitations within the Apple Home app for the two Brew By Weight settings and this has required the use of Thermostat accessories. They still allow the weights to be set, but they appear as degrees C, rather than grams and can only be set in 0.5 gram increments.

The machine API is subject to change and could render the project non-functional.

The project has only implemented a subset of the machine's API capabilities, to focus on the ones that benefit the most from Siri integration.


## License

This project is licensed under the MIT License - see the LICENSE.md file for details

