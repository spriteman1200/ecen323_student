#!/usr/bin/python3

'''
Script for extracting a student submission from a GitHub repository and
checking the submission.

TODO:
- Change instructions so that the students add the "--squash" flag on the merge so they don't get so
  many commits when they merge the starter code
- Squash the commit history of the starter code before the semester begins
- Checkout the starter code if it doesn't exist (or give a flag to the student code repository) and
  run the scripts from the known good repository.
'''

# Manages file paths
import pathlib
# Command line argunent parser
import argparse
# Get the username of the current user
import getpass
# Shell utilities for copying, 
import shutil
import subprocess
import sys
import re
# For os.remove
import os
# for File IO status flags
import stat
# for serialization
import pickle
# for time delay
import time

import lab_passoff
from lab_passoff import TermColor

class tester_module():
	""" Super class for all test modules """

	def module_name(self):
		''' returns a string indicating the name of the module. Used for logging. '''
		return "BASE MODULE"

	def perform_test(self, lab_test):
		''' This is the function that should be overridden by a test module. '''
		lab_test.print_print_warning("This should be overridden")
		return False

class simulation_module(tester_module):
	''' A tester module that performs simulations with Vivado tools
	'''

	def __init__(self, sim_top_module_name, hdl_sim_keylist):
		''' Initialize the top module name and the keylist for simulation HDL files '''
		self.sim_top_module = sim_top_module_name
		self.hdl_sim_keylist = hdl_sim_keylist

	def analyze_hdl_files(self, lab_test):
		''' Perform HDL analysis on a set of files '''
		
		# Resolve the filenames
		hdl_filename_list = lab_test.get_filenames_from_keylist(self.hdl_sim_keylist)

		# See if the executable is even in the path
		if not lab_test.check_executable_existence(["xvlog", "--version"]):
			return False

		# Analyze all of the files associated with the TCL simulation set
		lab_test.print_info(TermColor.BLUE, " Analyzing source files")
		for src_filename in hdl_filename_list:
			#print("  Analyzing File",src_filename)
			xvlog_cmd = ["xvlog", "--nolog", "-sv", src_filename ]
			proc = subprocess.run(xvlog_cmd, cwd=lab_test.execution_path, check=False)
			if proc.returncode:
				lab_test.print_error("Failed analyze of file ",src_filename)
				return False
		return True

	def elaborate(self, lab_test):
		# Elaborate design
		design_name = self.sim_top_module
		lab_test.print_info(TermColor.BLUE, " Elaborating")
		#xelab_cmd = ["xelab", "--debug", "typical", "--nolog", "-L", "unisims_ver", design_name, "work.glbl" ]
		xelab_cmd = ["xelab", "--debug", "typical", "--nolog", "-L", "unisims_ver", design_name ]
		proc = subprocess.run(xelab_cmd, cwd=lab_test.execution_path, check=False)

		#xelab_cmd = ["xelab", "--debug", "typical", "--nolog", design_name, "work.glbl" ]
		#xelab_cmd = ["xelab", "--debug", "typical", "--nolog", "-L xil_defaultlib", "-L unisims_ver", "-L unimacro_ver", design_name, "work.glbl" ]
		#xelab  -wto f006d1b2ec3040b5bab73404505d9a2c --debug typical --relax --mt 2 -L xil_defaultlib -L unisims_ver -L unimacro_ver -L secureip --snapshot riscv_io_system_behav xil_defaultlib.riscv_io_system xil_defaultlib.glbl -log elaborate.log    proc = subprocess.run(xelab_cmd, cwd=extract_path, check=False)
		if proc.returncode:
			lab_test.print_error("Error in elaboration")
			return False
		return True

	def simulate(self,lab_test,tcl_script_filename=None):
		# Simulate
		extract_lab_path = lab_test.submission_lab_path
		lab_test.print_info(TermColor.BLUE, " Starting Simulation")
		simulation_log_filename = str(self.sim_top_module + "_simulation.txt")
		simulation_log_filepath = extract_lab_path / simulation_log_filename
		# default simulation commands
		xsim_cmd = ["xsim", "-nolog", self.sim_top_module,]
		if tcl_script_filename:
			# TCL script
			xsim_cmd.append("-tclbatch")
			xsim_cmd.append(tcl_script_filename)
			pass
		else:
			# No TCL script
			xsim_cmd.append("-runall")
			pass

		if not lab_test.subprocess_file_print(simulation_log_filepath, xsim_cmd, lab_test.execution_path ):
			lab_test.print_error("Failed simulation")
			return False
		return True

class tcl_simulation(simulation_module):
	''' An object that represents a tcl_simulation test. Extends simulation_module
	'''
	def __init__(self,tcl_filename_key, tcl_sim_top_module, hdl_sim_keylist):
		super().__init__(tcl_sim_top_module,hdl_sim_keylist)

		self.tcl_filename_key = tcl_filename_key

	def module_name(self):
		''' returns a string indicating the name of the module. Used for logging. '''
		return str.format("TCL Simulation ({})",self.tcl_filename_key)

	def perform_test(self, lab_test):
		''' 
		Perform a simulation of a module with a Tcl script.
			sim_path: the path where the simulation should take place
			tcl_list: the list of items associated with a tcl simulation
		'''
		
		if not self.analyze_hdl_files(lab_test):
			return False
		if not self.elaborate(lab_test):
			return False

		lab_path = lab_test.submission_lab_path
		design_name = self.sim_top_module
		tcl_filename = lab_test.get_filename_from_key(self.tcl_filename_key)

		# Modify TCL simulation script (add 'quit' command to end)
		temp_tcl_filename = str(design_name + "_tempsim.tcl")
		src_tcl = lab_test.execution_path / tcl_filename
		tmp_tcl = lab_test.execution_path / temp_tcl_filename
		print(lab_test.execution_path,tmp_tcl,src_tcl)
		shutil.copyfile(src_tcl, tmp_tcl)

		log = open(tmp_tcl, 'a')
		log.write('\n# Add Exit quit command\n')
		log.write('quit\n')
		log.close()

		# Simulate
		return self.simulate(lab_test,temp_tcl_filename)


class testbench_simulation(simulation_module):
	''' An object that represents a tcl_simulation test.
	'''
	def __init__(self,testbench_description, testbench_top, hdl_sim_keylist, xe_options_list):
		super().__init__(testbench_top,hdl_sim_keylist)
		self.testbench_description = testbench_description
		#self.testbench_top = testbench_top
		#self.hdl_sim_keylist = hdl_sim_keylist
		self.xe_options_list = xe_options_list

	def module_name(self):
		''' returns a string indicating the name of the module. Used for logging. '''
		return str.format("Testbench Simulation \"{}\" ({})",self.testbench_description, self.sim_top_module)
		
	def perform_test(self, lab_test):
		''' 
		Perform a simulation of a module with a Tcl script.
			sim_path: the path where the simulation should take place
			tcl_list: the list of items associated with a tcl simulation
		'''
		
		hdl_filename_list = lab_test.get_filenames_from_keylist(self.hdl_sim_keylist)
		extract_lab_path = lab_test.submission_lab_path

		if not self.analyze_hdl_files(lab_test):
			return False
		if not self.elaborate(lab_test):
			return False

		return self.simulate(lab_test)


class build_bitstream(tester_module):
	''' An object that represents a tcl_simulation test.
	'''

	def __init__(self,design_name, xdl_key_list, hdl_key_list, implement_build = True, create_dcp = False):
		self.design_name = design_name
		self.xdl_key_list = xdl_key_list
		self.hdl_key_list = hdl_key_list
		self.implement_build = implement_build
		self.create_dcp = create_dcp

	def module_name(self):
		''' returns a string indicating the name of the module. Used for logging. '''
		return str.format("Synthesis/Bitstream Gen ({})",self.design_name)

	def perform_test(self, lab_test):

		part = lab_test.BASYS3_PART
		bitfile_filename = str(self.design_name + ".bit")
		dcp_filename = str(self.design_name + ".dcp")
		#extract_path = lab_test.submission_lab_path
		hdl_filenames = lab_test.get_filenames_from_keylist(self.hdl_key_list)
		xdl_filenames = lab_test.get_filenames_from_keylist(self.xdl_key_list)

		# Get name of new settings file (need to make it relative to execution path)
		rel_path = os.path.relpath(os.path.relpath(lab_test.submission_lab_path,lab_test.execution_path))
		new_path = os.path.join(rel_path,lab_test.NEW_PROJECT_SETTINGS_FILENAME)
		pre_script_filenames = [ new_path ]
		lab_test.print_info("Attempting to build bitfile",bitfile_filename)

		# Create tcl build script (the build will involve executing this script)
		tcl_build_script_filename = str(self.design_name + "_buildscript.tcl")
		tmp_tcl = lab_test.execution_path / tcl_build_script_filename

		log = open(tmp_tcl, 'w')
		log.write('# Bitfile Generation script (non-project mode)\n')
		log.write('#\n')
		if pre_script_filenames:
			log.write('# Pre-build source files\n')
			for pre_source_filename in pre_script_filenames:
				log.write('source '+ pre_source_filename+'\n')
		else:
			log.write('# No Pre-build script files\n')

		# Read HDL files
		log.write('# Add sources\n')
		for hdl_filename in hdl_filenames:
			#src = get_filename_from_key(src_key)
			log.write('read_verilog -sv ' + hdl_filename + '\n')
		# Read xdc files
		if self.implement_build:
			log.write('# Add XDC file\n')
			for xdc_filename in xdl_filenames:
				log.write('read_xdc ' + xdc_filename + '\n')
		log.write('# Synthesize design\n')
		#log.write('synth_design -top ' + design_name + ' -flatten_hierarchy full\n')
		log.write('synth_design -top ' + self.design_name + ' -part ' + part + '\n')
		if self.implement_build:    
			log.write('# Implement Design\n')
			log.write('place_design\n')
			log.write('route_design\n')
			checkpoint_filename = str(self.design_name + ".dcp")
			log.write('write_checkpoint ' + checkpoint_filename + ' -force\n')
			log.write('write_bitstream -force ' + bitfile_filename +'\n')
		if self.create_dcp:
			log.write('# Create DCP\n')
			log.write(str.format("write_checkpoint {} -force\n",dcp_filename))
		log.write('# End of build script\n')
		log.close()

		# See if the executable is even in the path
		if not lab_test.check_executable_existence(["vivado", "-version"]):
			return False

		implementation_log_filename = str(self.design_name + "_implementation.txt")
		implementation_log_filepath = lab_test.execution_path / implementation_log_filename
		with open(implementation_log_filepath, "w") as fp:
			build_cmd = ["vivado", "-nolog", "-mode", "batch", "-nojournal", "-source", tcl_build_script_filename]
			proc = subprocess.Popen(
				build_cmd,
				cwd=lab_test.execution_path,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				universal_newlines=True,
			)
			for line in proc.stdout:
				sys.stdout.write(line)
				fp.write(line)
				fp.flush()
			# Wait until process is done
			proc.communicate()
			if proc.returncode:
				#print("Error with implement")
				return False
		return True