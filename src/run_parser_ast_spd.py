#!/home/shinji/.linuxbrew/bin/python

# -*encoding utf8-*
import os
import sys
import re
from clang.cindex import Index
import subprocess
import shlex


"""
This program is for making input SPD of padtool(*1).
The way of running of this program is as following,

1. run this with a function name which you want to make SPD of.
2. firstly, search the source file where the function is defined (use global/gtags)
3. then, run clang python bindings, and get function AST
4. then, parse the AST
5. lastly, output with format SPD.
"""




"""
#TODO 
The libclang will output lots of fields corresponding to C-source. See < http://clang.llvm.org/doxygen/ >.
The following is some of them (it's just extract from one source code, and is subset of libclang supported)

ArraySubscriptExpr BinaryOperator BreakStmt CallExpr CaseStmt CharacterLiteral CompoundAssignOperator
CompoundStmt ConditionalOperator ContinueStmt CStyleCastExpr DeclRefExpr DeclStmt DefaultStmt ForStmt
GotoStmt IfStmt ImplicitCastExpr InitListExpr IntegerLiteral LabelStmt MemberExpr ParenExpr ReturnStmt
StringLiteral SwitchStmt UnaryExprOrTypeTraitExpr UnaryOperator WhileStmt

Firstly, we just support

A. ForStmt/WhileStmt/IfStmt/SwitchStmt/SwichCase/ which are basic flow control statements.
B. BreakStmt/ContinueStmt/GotoStmt/DefaultStmt/LavelStmt/ReturnStmt/DeclStmt/ which are basic build-in keywords.


"""

class ClangSPD:
    def __init__(self):
        self.obj = None
        self.output = []
        self.function = ""
        self.filename = ""
        self.verbose = False

    def __del__(self):
        del self.obj
        del self.output
    #END __del__

    def perror(self, Message):
	""" print message verbosely """
	mydict = {
            "ERR_GTAGS":"failed to create GTAGS file",
            "ERR_GLOBAL": "failed to search target function",
            "ERR_NO_FUNCDEF": "failed to find target function declare",
            "ERR_NO_MATCH_FUNC" : "failed to find function name in clang AST",
            "WARN_ONE_MORE_DEF": "find more than one definition" }
	if re.match(r"ERR.*", Message):
            if self.verbose:
                print "Error: " + mydict[Message]
            sys.exit(99)
	elif re.match(r"WARN.*", Message):
            if self.verbose:
                print "Warning: " + mydict[Message]
    #END perror

    def getFilename(self):
	""" Get File(where specified function is in) if not specified """
	if not os.path.exists("GTAGS"):
            try:
                subprocess.check_call(shlex.split("gtags -v"))
            except CalledProcessError:
                self.perror("ERR_GTAGS")
	try:
            (output) = subprocess.check_output(shlex.split("global -x " + options.function))
	except CalledProcessError:
            self.perror("ERR_GLOBAL")

	tmp = output.split("\n")
	if len(tmp) == 0:
            self.perror("ERR_NO_FUNCDEF")
	if len(tmp) >= 3:
            self.perror("WARN_ONE_MORE_DEF")
        tfilename = filter(lambda s:s != '', tmp[0].split(" "))
	return tfilename[2]
    #END getFilename

    def setOptions(self,options):
	# self.iter holds the depth of iteration.
	# in the most upper layer, we should process function name.
	self.iter = 0

	# self.output holds the output string with SPD format.
	# the string should be split by "\n" digit.
	self.output = []

	self.obj = None

        if options.count:
            self.count = options.count
        else:
            self.count = 0

        if options.options:
            tmp = "".join(options.options)
            self.options = tmp.split(" ")
        else:
            self.options = None

	if options.function:
            self.function = options.function

	if options.verbose:
            self.verbose = True
	else:
            self.verbose = False

	if options.filename:
            self.filename = options.filename
	else:
            self.filename = self.getFilename()
    #END setOptions

    def getClangObject(self):
	"""
	need import clang.cindex and Index
	just return the cursor object, which points to the target function
	"""
	index = Index.create()
        if self.options:
            tu = index.parse(self.filename, args = self.options)
        else:
            tu = index.parse(self.filename)
        tmpCnt = 0
	for obj in tu.cursor.get_children():
            if obj.spelling == self.function:
                if tmpCnt != int(self.count):
                    tmpCnt = tmpCnt + 1
                    continue
                #here we succeeded in finding
                self.obj = obj
                del index
                del tu
                return True
	# in this case: we find it is error(just return when reaching here)
	del index
	del tu
	return False
    #END getClangObject

    def __getTokens__(self,obj):
        """
        obj is clang.cindex.cursor type:
        stopwords should be selected due to statements
        e.g., "IF_STMT" --> [";", ")"]
              "CASE_STMT" --> [":"]
        FIXME: in IF_STMT and RETURN_STMT, we cannot delete ";"...
        """
        # this will return concatinated string
        tmpStr = ""
        stopwords = {
                "IF_STMT":")",
                "SWITCH_STMT":")",
                "FOR_STMT":")",
                "WHILE_STMT":")",
                "CASE_STMT": ":",
                "DEFAULT_STMT": ":",
                "LABEL_STMT": ":",
                "RETURN_STMT": ";",
                "GOTO_STMT": ";",
                "BREAK_STMT": ";",
                "DECL_STMT": ";",
                "VAR_DECL": ";"
                }
        if obj.kind.name in stopwords:
            for tt in obj.get_tokens():
                if tt.spelling is stopwords[obj.kind.name]:
                    if stopwords[obj.kind.name] == ")":
                        if tmpStr.count("(") == tmpStr.count(")") + 1:
                            tmpStr = tmpStr + " " + tt.spelling 
                            break
                    else:
                        break
                tmpStr = tmpStr + " " + tt.spelling
        else:
            for tt in obj.get_tokens():
                tmpStr = tmpStr + " " + tt.spelling

        if obj.kind.name == "DO_STMT":
            tmpStr = re.search(r".*while(.*)", tmpStr).group(1)
            tmpStr = tmpStr
        #end for searching tokens
        return tmpStr.lstrip(" ")
    #END __getTokens__

    mydict = {
            "IF_STMT": ":if ",
            "WHILE_STMT": ":while ",
            "DO_STMT": ":dowhile ",
            "FOR_STMT": ":while ",
            "SWITCH_STMT": ":switch ",
            "CASE_STMT":":case ",
            "DEFAULT_STMT":":case "
    }

    def __actLoop__(self,obj, indent, call_from, depth):
        """ 
        this is the main recursive function called from mainParser
        this will proceed depth-prior search in TransactionUnit of libclang
        when encountering some statement(stmt) or expression(expr), corresponding procedure will be done
        """
        for (cnt, step) in enumerate(obj.get_children()):

            """ Statement(STMT) parsing """

            if step.kind.name is "COMPOUND_STMT":
                if call_from is "IF_STMT":
                    # if in if_stmt, compound_stmt never used in cnt == 0
                    if cnt == 1:
                       self.__actLoop__(step, indent, step.kind.name, depth+1)
                    elif cnt == 2:
                        self.output.append(indent[1:] + ":else\n")
                        self.__actLoop__(step, indent, step.kind.name, depth+1)
                elif call_from in ["", "WHILE_STMT", "FOR_STMT", "SWITCH_STMT", "DO_STMT"]:
                    self.__actLoop__(step, indent , step.kind.name, depth+1)
                elif call_from in ["CASE_STMT", "DEFAULT_STMT"]:
                    self.__actLoop__(step, indent, step.kind.name, depth+1)

            #end compound_stmt
            if step.kind.name in ["WHILE_STMT", "FOR_STMT", "SWITCH_STMT", "DO_STMT"]:
                #add :while/for/switch/do
                #we've assumed these are called from compound_stmt
                self.output.append(indent + self.mydict[step.kind.name] + self.__getTokens__(step) + "\n")
                self.__actLoop__(step, indent + "\t", step.kind.name, depth+1)
            #end {while,for,switch,do}_stmt

            if step.kind.name in ["IF_STMT"]:
                #add :if
                #we've assumed these are called from {if(else), while, for, compound}_stmt
                if call_from is "IF_STMT" and cnt == 2:
                    self.output.append(indent[1:] + ":else\n")
                    self.output.append(indent + self.mydict[step.kind.name] + self.__getTokens__(step) + "\n")
                    self.__actLoop__(step, indent + "\t", step.kind.name, depth+1)
                else:
                    self.output.append(indent + self.mydict[step.kind.name] + self.__getTokens__(step) + "\n")
                    self.__actLoop__(step, indent + "\t", step.kind.name, depth+1)
            #end if_stmt

            if step.kind.name in ["CASE_STMT", "DEFAULT_STMT"]:
                # case_stmt is odd, it's in the same indent level as switch, 
                # and continue while other stmt or operator apperes
                self.output.append(indent[1:]+ self.mydict[step.kind.name] + self.__getTokens__(step) + "\n")
                self.__actLoop__(step, indent[0:], step.kind.name, depth + 1)
            #end case_stmt

            if step.kind.name is "DECL_STMT":
                # decr_stmt is just for var_decl; put call_from
                self.output.append(indent + self.__getTokens__(step) + "\n")
                #self.__actLoop__(step, indent, step.kind.name, depth + 1)

            if step.kind.name in ["CONTINUE_STMT", "RETURN_STMT", "BREAK_STMT", "GOTO_STMT"]:
                # read argument(if there), and just print
                self.output.append(indent + self.__getTokens__(step) + "\n")
            if step.kind.name is "LABEL_STMT":
                # label is one of statement !, which means label can contain sub steps
                self.output.append(indent + self.__getTokens__(step) + "\n")
                self.__actLoop__(step, indent, step.kind.name, depth + 1)

            """ Operator, Expression and Declare(DECL) parsing """

            #if step.kind.name in ["VAR_DECL"]:
            #    # read until token end
            #    self.output.append(indent + self.__getTokens__(step) + "\n")
            ##end if VAR_DECL

            if step.kind.name in ["BINARY_OPERATOR","CALL_EXPR"]:
                # This is the Main Main Main target
                # it's very important where this is called
                if call_from in ["COMPOUND_STMT"]:
                    # no need bother, just print
                    self.output.append(indent + self.__getTokens__(step) + "\n")
                if (call_from in ["WHILE_STMT", "CASE_STMT", "DEFAULT_STMT"] and cnt == 1) or (call_from in ["DO_STMT"] and cnt == 0):
                    # it's rare case (such as while(1) a++; ) --> switch never meets
                    self.output.append(indent + self.__getTokens__(step) + "\n")
                if call_from in ["FOR_STMT"]:
                    # it's hard to identify where the boperation is in for_stmt (consider:  for(;;) b++;)
                    tmpcnt = 0
                    for tmpstep in obj.get_children():
                        tmpcnt = tmpcnt + 1
                    if cnt == tmpcnt:
                        # this is the only case
                        self.output.append(indent + self.__getTokens__(step) + "\n")

                if call_from is "IF_STMT" and cnt in [1,2]:
                    # when if_stmt, just consder A and B in if(<cond>){A}else{B} 
                    self.output.append(indent + self.__getTokens__(step) + "\n")
            #end binary_operator

            #TODO: Should we add more considerations such as COMPOUND_ASSIGNMENT_OPERATOR ?

            # ignore other ones

    #End actLoop

    def mainParser(self):
        """
	we will parse the statements under the object(return from getClangObject)
	it is recursive function which call itself.
	The deeper the depth of recursion becomes, the more indents(tabs) are to be added.

	IF_STMT :
	    BINARY_OPERATOR argc == 1
		    UNEXPOSED_EXPR : argc
			    DECL_REF_EXPR : argc
		    INTEGER_LITERAL :
	    COMPOUND_STMT :
		    DECL_STMT :
			    VAR_DECL : s
				    INTEGER_LITERAL :
		    CALL_EXPR : printf
        """
	## In the zero step, we should add ":terminal functionName(hogehoge)\n"
	tmpStr = ":terminal "
        for fargs in self.obj.get_tokens():
            if fargs.spelling  == "{":
                break
            tmpStr = tmpStr + " " +fargs.spelling

	#end for
	self.output.append(tmpStr + "\n")

	## In the first step, find COMPOUND_STMT in the function:
	## FIXME: this is odd code... should be more flexsible one (for such as inline asm or macro function)
	for first in self.obj.get_children():
            if first.kind.name == "COMPOUND_STMT":
                # we find it ! Then we focus on this statement(search in this)
                break
            #end if
	#end for

	# call recursive function __actLoop__
	self.__actLoop__(first, "", first.kind.name, 0)

	# After the recursion, we should close the PAD by ":terminal END\n"
	self.output.append(":terminal END\n")
    #END mainParser

    def printSPD(self):
	"""
	This function outputs data with SPD format.
	Only print to STDOUT for each element in list self.output.
	Note: we should not enter any LF(\n) for each printing, 
	e.g., each string in the list should have "\n" (such as ["hogehoge\n", "foobar\n"])
	"""
	for element in self.output:
            print element,
	#end for
    #END printSPD

#END class ClangSPD




if __name__ == "__main__":

    from optparse import OptionParser

    # call instructor
    clangobj = ClangSPD()

    """ Option Parser """
    #parser = argparse.ArgumentParser(description='')
    parser = OptionParser()
    parser.add_option("-f", "--file", dest="filename",
                    help = "specify the file where the function may defined",metavar = "FILE")
    parser.add_option("-v", "--verbose",action="store_false",dest="verbose",
                    help = "run under verbose mode")
    parser.add_option("-F", "--function", dest="function",default=True,
                    help = "specify a function for which you want to make SPD.", metavar="FUNC")
    parser.add_option("-O", "--options", dest="options",
                    help = "specify the options to pass clang", metavar="OPTS")
    parser.add_option("-C", "--count", dest="count",
                    help = "specify how many times to find the definition", metavar="COUNT")
    (options, args) = parser.parse_args()


    # now we have at least target function name...
    # first set the options to object
    clangobj.setOptions(options)

    # second, getFilename where the target function is
    clangobj.getFilename()

    # load clang library(libclang python bindings)
    if not clangobj.getClangObject():
            clangobj.perror("ERR_NO_MATCH_FUNC")
    #end if

    # run recursive function for creating SPD
    clangobj.mainParser()

    # output the SPD to STDOUT
    clangobj.printSPD()

    # lastly, cleanup the clangobj
    del clangobj

#END __main__
