import unittest
import os
import shutil
import tempfile
import csv
from t8_daq_system.data.data_logger import DataLogger

class TestDataLogger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.logger = DataLogger(log_folder=self.test_dir)

    def tearDown(self):
        self.logger.stop_logging()
        shutil.rmtree(self.test_dir)

    def test_start_logging(self):
        sensor_names = ['TC1', 'P1']
        filepath = self.logger.start_logging(sensor_names)
        
        self.assertTrue(os.path.exists(filepath))
        self.assertTrue(self.logger.is_logging())
        
        # Check header
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['Timestamp', 'TC1', 'P1'])

    def test_log_reading(self):
        sensor_names = ['TC1', 'P1']
        filepath = self.logger.start_logging(sensor_names)
        
        readings = {'TC1': 25.5, 'P1': 100.2}
        self.logger.log_reading(readings)
        self.logger.stop_logging()
        
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader) # skip header
            data = next(reader)
            self.assertEqual(data[1], '25.5')
            self.assertEqual(data[2], '100.2')

    def test_get_log_files(self):
        self.logger.start_logging(['S1'])
        self.logger.stop_logging()
        
        files = self.logger.get_log_files()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith('.csv'))

if __name__ == '__main__':
    unittest.main()
