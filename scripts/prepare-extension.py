#!/usr/bin/env python3
"""Prepare a standalone extension from a Designer XML export of FormEditor."""

import argparse
from pathlib import Path
import shutil
import uuid
from xml.dom import minidom


MD = "http://v8.1c.ru/8.3/MDClasses"


def child(parent, name):
    if parent is None:
        return None
    return next((node for node in parent.childNodes
                 if node.nodeType == node.ELEMENT_NODE
                 and node.namespaceURI == MD and node.localName == name), None)


def prepare(source: Path, destination: Path) -> None:
    # Never overwrite an existing directory: it may contain an export or infobase.
    tree = minidom.parse(str(source / "Configuration.xml"))
    configuration = child(tree.documentElement, "Configuration")
    if configuration is None:
        raise ValueError("Expected a Designer XML export with Configuration.xml")
    properties = child(configuration, "Properties")
    children = child(configuration, "ChildObjects")
    if properties is None or children is None:
        raise ValueError("Configuration Properties or ChildObjects are missing")
    module = source / "CommonModules" / "РедакторФорм.xml"
    module_tree = minidom.parse(str(module))
    module_object = child(module_tree.documentElement, "CommonModule")
    module_properties = child(module_object, "Properties")
    if module_properties is None:
        raise ValueError("Common module Properties are missing")
    module_code = source / "CommonModules" / "РедакторФорм" / "Ext" / "Module.bsl"
    if not module_code.is_file():
        raise FileNotFoundError(module_code)

    def set_property(parent, name, value):
        element = child(parent, name)
        if element is None:
            element = parent.ownerDocument.createElementNS(MD, name)
            if name == "ObjectBelonging":
                parent.insertBefore(element, parent.firstChild)
            else:
                parent.appendChild(element)
        while element.firstChild:
            element.removeChild(element.firstChild)
        element.appendChild(parent.ownerDocument.createTextNode(value))

    set_property(properties, "Name", "FormEditor")
    set_property(properties, "ObjectBelonging", "Adopted")
    configuration.setAttribute("uuid", str(uuid.uuid5(
        uuid.NAMESPACE_URL, "formeditor-extension:" + configuration.getAttribute("uuid"))))
    set_property(properties, "ConfigurationExtensionPurpose", "AddOn")
    set_property(properties, "NamePrefix", "рф_")
    set_property(properties, "KeepMappingToExtendedConfigurationObjectsByIDs", "false")
    # The library has no dependencies on the demo configuration's language or UI.
    for element in list(properties.childNodes):
        if element.nodeType == element.ELEMENT_NODE and element.localName in {
            "DefaultLanguage", "DefaultRoles", "DefaultRole", "MainSection",
            "HomePageWorkArea", "DefaultInterface", "DefaultStyle",
        }:
            properties.removeChild(element)
    while children.firstChild:
        children.removeChild(children.firstChild)
    element = tree.createElementNS(MD, "CommonModule")
    element.appendChild(tree.createTextNode("РедакторФорм"))
    children.appendChild(element)
    set_property(module_properties, "ObjectBelonging", "Native")

    destination.mkdir(parents=True, exist_ok=False)
    (destination / "CommonModules").mkdir()
    shutil.copytree(source / "CommonModules" / "РедакторФорм",
                    destination / "CommonModules" / "РедакторФорм")
    (destination / "Configuration.xml").write_bytes(tree.toxml(encoding="utf-8"))
    (destination / "CommonModules" / "РедакторФорм.xml").write_bytes(
        module_tree.toxml(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Designer XML export from EDT")
    parser.add_argument("destination", type=Path, help="New extension XML directory")
    args = parser.parse_args()
    prepare(args.source, args.destination)
