from html.parser import HTMLParser
import csv
import os
import subprocess
import shutil
import fileinput
from datetime import datetime

jacoco_path = '/target/site/jacoco/index.html'
current_datetime = datetime.now().strftime("%m.%d.%y_%H:%M:%S")
log_folder = f"hadoop_puts_logs_{current_datetime}/"
os.makedirs(log_folder)
enable = True
first = False

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_total_td = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag == "td" and ("class", "bar") in attrs:
            self.in_total_td = True

    def handle_data(self, data):
        if self.in_total_td:
            value = data.strip().replace(",", "")
            self.values.append(value)

    def handle_endtag(self, tag):
        if self.in_total_td and tag == "td":
            self.in_total_td = False

def get_values_from_html_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
        parser = MyHTMLParser()
        parser.feed(html_content)
        return parser.values

def get_coverage_details_from_html(file_path):
    covered_instructions =0
    total_instructions =0
    covered_branches=0
    total_branches =0
    if os.path.exists(file_path):
        values = get_values_from_html_file(file_path)
    #     print(values)
        missed_instructions, total_instructions = map(int, values[0].split(" of "))
        missed_branches, total_branches = map(int, values[1].split(" of "))
        covered_instructions = total_instructions-missed_instructions
        covered_branches = total_branches-missed_branches
    return [covered_instructions, total_instructions, covered_branches, total_branches]

def getTestRunNumber(log_file):
   with open(log_file) as log:
        for line in log:
            if "Tests run:" in line:
#             Tests run: 192, Failures: 44, Errors: 16, Skipped: 96
                all=line.strip().split(', ')
                tests_run=int(all[0].split(': ')[1])
                failures=int(all[1].split(': ')[1])
                errors=int(all[2].split(': ')[1])
                skipped=int(all[3].split(': ')[1])
                passed = tests_run - failures - errors - skipped
                return [passed, failures, errors, skipped]
def get_test_param_number(log_file):
# Add logic to also get the number of initial and resulting combination parameters
# Number of unique values for each parameter:4 x 2 x 2 x 4 x 3 = 192
    with open(log_file) as log:
        for line in log:
            if "Number of unique values for each parameter:" in line:
                # Number of unique values for each parameter:4 x 2 x 2 x 4 x 3 = 192
                paramData=line.strip().split("Number of unique values for each parameter:")[1]
                return paramData
def print_info(info):
    if enable:
        print(info)

def run_for_all(csv_f):
    with open(csv_f, newline='') as file:
        csv_reader = csv.DictReader(file)
        i=0
        for row in csv_reader:
            test_name = row['Fully-Qualified Test Name']
            module_path = row['Module Path']
            try:
                test_full_path=module_path + "/src/test/java/" + test_name.replace('.', '/').split('#')[0] + ".java"
                command = f"mvn test -Dtest={test_name}[\\*] -pl {module_path}"
                log_file = f"{log_folder}{test_name.replace('#', '_')}.log"

                print("Running command:", command)
                with open(log_file, 'w') as log:
                    subprocess.run(command, shell=True, stdout=log, stderr=subprocess.STDOUT)
                coverageData = get_coverage_details_from_html(module_path + jacoco_path)
                run_data = getTestRunNumber(log_file)
                print("CoverageData for test :", test_name, coverageData)
                print("RunData for test :", test_name, run_data)

                clean_jacoco(module_path)

                #already modified to run with Cartesian
                modify_test(test_full_path)

                #Now we should run it again
                log_file2 = f"{log_folder}{test_name.replace('#', '_')}2.log"
                print("Running command:", command)
                with open(log_file2, 'w') as log:
                    subprocess.run(command, shell=True, stdout=log, stderr=subprocess.STDOUT)

                param_number_info = get_test_param_number(log_file2)
                if param_number_info is not None and 'x' not in param_number_info:
                    raise Exception("Skipping the test as it has just 1 parameter")
                coverage_data_c = get_coverage_details_from_html(module_path + jacoco_path)
                run_data_c = getTestRunNumber(log_file2)
                print("CoverageData2 for test :", test_name, coverage_data_c)
                print("Tests Run data2 for test:", test_name, run_data_c)
                print("Param data for test:", test_name, param_number_info)


                writeCSV(test_name, module_path, coverageData, run_data, coverage_data_c, run_data_c, param_number_info)
                first = False
                clean_jacoco(module_path)
                modify_test(test_full_path, False)
            except Exception as error:
                i=i+1
                # Restore the data if there was a failure
                clean_jacoco(module_path)
                modify_test(test_full_path, False)
                print("An error occurred when processing: ", test_name, ":" , type(error).__name__, "–", error)
        print(i, " tests have been skipped")
def clean_jacoco(module_path):
    jacoco_directory = module_path + "/target/site/jacoco"
    jacoco_exec_file = module_path + "/target/jacoco.exec"
    if os.path.exists(jacoco_directory):
        shutil.rmtree(jacoco_directory)
    if os.path.exists(jacoco_exec_file):
        os.remove(jacoco_exec_file)

def modify_test(file_path, make_cartesian=True):
    with fileinput.FileInput(file_path, inplace=True) as file:
        for line in file:
            if make_cartesian:
                line = line.replace('import org.junit.runners.Parameterized;', 'import edu.illinois.Parameterized;')
                line = line.replace('import org.junit.runners.Parameterized.Parameters;', 'import edu.illinois.Parameterized.Parameters;')
            else:
                line = line.replace('import edu.illinois.Parameterized;', 'import org.junit.runners.Parameterized;')
                line = line.replace('import edu.illinois.Parameterized.Parameters;', 'import org.junit.runners.Parameterized.Parameters;')
            print(line, end='')

def writeCSV(test_name,module_path , coverage_data, run_data, coverage_data_c, run_data_c, param_number_info):
    csv_filename = f"put_data.csv"
    with open(csv_filename, "a", newline="") as csvfile:
        fieldnames = ["Project URL", "Module Path", "Fully-Qualified Test Name","ParameterCombinations",
                      "CoveredInstructions", "CoveredBranches", "Passed", "Failure", "Errors", "Skipped",
                      "CoveredInstructions_C", "CoveredBranches_C", "Passed_C", "Failure_C", "Errors_C", "Skipped_C", "CoverageChange"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        # Write the header only if the file is empty
        if(first):
            writer.writeheader()
        writer.writerow({
            "Project URL": "Hadoop",
            "Module Path": module_path,
            "Fully-Qualified Test Name": test_name,
            "ParameterCombinations": param_number_info,
            "CoveredInstructions": coverage_data[0],
            "CoveredBranches": coverage_data[2],
            "Passed": run_data[0],
            "Failure": run_data[1],
            "Errors": run_data[2],
            "Skipped": run_data[3],
            "CoveredInstructions_C": coverage_data_c[0],
            "CoveredBranches_C": coverage_data_c[2],
            "Passed_C": run_data_c[0],
            "Failure_C": run_data_c[1],
            "Errors_C": run_data_c[2],
            "Skipped_C": run_data_c[3],
            "CoverageChange":coverage_data_c[0] - coverage_data[0],
        })

if __name__ == "__main__":
    first = True
    csv_file = 'hadoop_parameterized_tests.csv'
    run_for_all(csv_file)

