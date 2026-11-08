import importlib.util
from pathlib import Path
import tempfile
import unittest
from xml.dom import minidom


spec = importlib.util.spec_from_file_location(
    "prepare_extension", Path(__file__).parents[1] / "scripts/prepare-extension.py")
extension = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extension)


class PrepareExtensionTest(unittest.TestCase):
    def test_library_export_preserves_module_and_namespace_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            module = source / "CommonModules" / "РедакторФорм"
            module.mkdir(parents=True)
            (module / "Ext").mkdir()
            code = (Path(__file__).parents[1] / "FormEditor/src/CommonModules/РедакторФорм/Module.bsl").read_bytes()
            (module / "Ext/Module.bsl").write_bytes(code)
            (source / "Configuration.xml").write_text(f'''<MetaDataObject xmlns="{extension.MD}" xmlns:v8="http://v8.1c.ru/8.1/data/core">
              <Configuration uuid="test"><Properties><Name>Demo</Name>
              <DefaultLanguage>Language.Русский</DefaultLanguage><Version>1.0</Version>
              <DefaultRoles/><Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Редактор</v8:content></v8:item></Synonym>
              </Properties><ChildObjects><Language>Русский</Language>
              <CommonModule>РедакторФорм</CommonModule><DataProcessor>Demo</DataProcessor>
              </ChildObjects></Configuration></MetaDataObject>''')
            (source / "CommonModules/РедакторФорм.xml").write_text(f'''<MetaDataObject xmlns="{extension.MD}" xmlns:xs="http://www.w3.org/2001/XMLSchema">
              <CommonModule uuid="module"><Properties><Name>РедакторФорм</Name>
              <Server>true</Server><Comment>xs:string</Comment></Properties></CommonModule></MetaDataObject>''')
            target = root / "extension"
            extension.prepare(source, target)
            document = minidom.parse(str(target / "Configuration.xml"))
            configuration = extension.child(document.documentElement, "Configuration")
            properties = extension.child(configuration, "Properties")
            self.assertEqual(extension.child(properties, "ConfigurationExtensionPurpose").firstChild.data, "AddOn")
            self.assertEqual(extension.child(properties, "ObjectBelonging").firstChild.data, "Adopted")
            self.assertIsNone(extension.child(properties, "DefaultLanguage"))
            children = extension.child(configuration, "ChildObjects")
            self.assertEqual([n.localName for n in children.childNodes if n.nodeType == n.ELEMENT_NODE], ["CommonModule"])
            self.assertEqual((target / "CommonModules/РедакторФорм/Ext/Module.bsl").read_bytes(), code)
            module_doc = minidom.parse(str(target / "CommonModules/РедакторФорм.xml"))
            self.assertEqual(module_doc.documentElement.getAttribute("xmlns:xs"), "http://www.w3.org/2001/XMLSchema")
            self.assertNotEqual(configuration.getAttribute("uuid"), "test")
            another_target = root / "extension-again"
            extension.prepare(source, another_target)
            another = minidom.parse(str(another_target / "Configuration.xml"))
            self.assertEqual(extension.child(another.documentElement, "Configuration").getAttribute("uuid"),
                             configuration.getAttribute("uuid"))
            properties = extension.child(extension.child(module_doc.documentElement, "CommonModule"), "Properties")
            self.assertEqual(extension.child(properties, "ObjectBelonging").firstChild.data, "Native")
            with self.assertRaises(FileExistsError):
                extension.prepare(source, target)
            self.assertEqual((target / "CommonModules/РедакторФорм/Ext/Module.bsl").read_bytes(), code)

    def test_invalid_export_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Configuration.xml").write_text("<unexpected/>")
            with self.assertRaises(ValueError):
                extension.prepare(root, root / "output")
            self.assertFalse((root / "output").exists())

    def test_missing_module_code_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "CommonModules").mkdir()
            (root / "Configuration.xml").write_text(f'''<MetaDataObject xmlns="{extension.MD}">
              <Configuration><Properties/><ChildObjects/></Configuration></MetaDataObject>''')
            (root / "CommonModules/РедакторФорм.xml").write_text(f'''<MetaDataObject xmlns="{extension.MD}">
              <CommonModule><Properties/></CommonModule></MetaDataObject>''')
            with self.assertRaises(FileNotFoundError):
                extension.prepare(root, root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
