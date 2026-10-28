/**
 * This file is part of Darling.
 *
 * Copyright (C) 2021 Darling developers
 *
 * Darling is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Darling is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Darling.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <darlingserver/process.hpp>
#include <darlingserver/registry.hpp>
#include <sys/syscall.h>
#include <unistd.h>
#include <sys/uio.h>
#include <darlingserver/logging.hpp>
#include <darlingserver/proc-maps.hpp>

#include <fstream>
#include <regex>
#include <sstream>
#include <atomic>

#include <sys/mman.h>
#include <sys/sysmacros.h>

static DarlingServer::Log processLog("process");
// Like XNU's nextpidversion, this changes on both fork and successful exec.
// The registry EternalID instead identifies the whole process lifetime.
static std::atomic<uint32_t> nextPIDVersion{1};

DarlingServer::Process::Process(ID id, NSID nsid, Architecture architecture, int pipe):
	_pid(id),
	_nspid(nsid),
	_architecture(architecture)
{
	int pidfd = (pipe >= 0) ? pipe : syscall(SYS_pidfd_open, _pid, 0);
	if (pidfd < 0) {
		throw std::system_error(errno, std::generic_category(), "Failed to open pidfd for process");
	}

	_pidfd = std::make_shared<FD>(pidfd);
	// Match libproc's existing Darwin unique-ID representation, using the real
	// Linux process birth time and the PID in the client's namespace. Never look
	// up a responsible PID later: PID reuse must not substitute a new process.
	std::ifstream statFile("/proc/" + std::to_string(id) + "/stat");
	std::string statLine;
	std::getline(statFile, statLine);
	auto endComm = statLine.rfind(')');
	if (endComm == std::string::npos) {
		throw std::system_error(ESRCH, std::generic_category(), "Missing process birth record");
	}
	std::istringstream statFields(statLine.substr(endComm + 1));
	std::string field;
	for (int number = 3; number <= 22; ++number) {
		if (!(statFields >> field)) {
			throw std::system_error(ESRCH, std::generic_category(), "Incomplete process birth record");
		}
	}
	_uniqueID = (std::stoull(field) << 16) | (_nspid & 0xffff);

	// we could use stat instead of status, but it's more complicated with comm potentially getting in the way of parsing (it can include whitespace and parentheses)
	std::ifstream statusFile("/proc/" + std::to_string(id) + "/status");
	std::string line;

	std::shared_ptr<Process> parentProcess = nullptr;

	while (std::getline(statusFile, line)) {
		if (line.substr(0, sizeof("PPid") - 1) == "PPid") {
			auto pos = line.find_last_of('\t');
			std::string id;

			if (pos != line.npos) {
				id = line.substr(pos + 1);
			}

			if (id.empty()) {
				throw std::runtime_error("Failed to parse parent process ID");
			}

			if (auto maybeParentProcess = processRegistry().lookupEntryByID(std::stoi(id))) {
				parentProcess = *maybeParentProcess;
				_parentProcess = parentProcess;
			}

			break;
		}
	}

	if (parentProcess) {
		std::shared_lock parentLock(parentProcess->_rwlock);

		// inherit vchroot from parent process
		_vchrootDescriptor = parentProcess->_vchrootDescriptor;
		_cachedVchrootPath = parentProcess->_cachedVchrootPath;

		// inherit groups from parent process
		_groups = parentProcess->_groups;
		_responsibility = parentProcess->_responsibility;
		_sandboxState = parentProcess->_sandboxState;
		_sandboxPolicy = parentProcess->_sandboxPolicy;
		_quarantineState = parentProcess->_quarantineState;
		_auditSession = parentProcess->_auditSession;
		_auditMaskSuccess = parentProcess->_auditMaskSuccess;
		_auditMaskFailure = parentProcess->_auditMaskFailure;
		_quarantineKernelCapabilities = parentProcess->_quarantineKernelCapabilities;
	}

    if (!_auditSession) {
        // Establish a headless bootstrap session for a process with no parent
        // managed by this server. Credentials come from its actual Linux proc
        // record; no graphics/TTY capability is claimed.
        std::ifstream credentials("/proc/" + std::to_string(_pid) + "/status");
        uint32_t uid=UINT32_MAX;
        while (std::getline(credentials,line)) {
            if (line.compare(0,4,"Uid:")==0) {
                std::istringstream fields(line.substr(4));
                if (!(fields>>uid)) throw std::system_error(ESRCH,std::generic_category());
                break;
            }
        }
        if (uid==UINT32_MAX) throw std::system_error(ESRCH,std::generic_category());
        darling_audit_info_t info{};
        info.auid=uid;
        info.terminal_type=4; // AU_IPv4, default terminal identity
        _auditSession=AuditSession::create(info);
    }

	// NOTE: see thread.cpp for why it's okay to use `this` here
	_dtapeTask = dtape_task_create(parentProcess ? parentProcess->_dtapeTask : nullptr, _nspid, this, static_cast<dserver_rpc_architecture_t>(_architecture));
	_dtapeForkWaitSemaphore = dtape_semaphore_create(_dtapeTask, 0);
    dtape_task_set_audit_identity(_dtapeTask, _auditSession->info.auid, _auditSession->info.asid);

	processLog.info() << "New process created with ID " << _pid << " and NSID " << _nspid;
};

DarlingServer::Process::Process(KernelProcessConstructorTag tag):
	_pid(-1),
	_nspid(0)
{
#if __x86_64__
	_architecture = Architecture::x86_64;
#elif __i386__
	_architecture = Architecture::i386;
#elif __aarch64__
	_architecture = Architecture::ARM64;
#elif __arm__
	_architecture = Architecture::ARM32;
#else
	#error Unknown architecture
#endif
	_dtapeTask = dtape_task_create(nullptr, _nspid, this, static_cast<dserver_rpc_architecture_t>(_architecture));
};

DarlingServer::Process::~Process() {
	processLog.info() << *this << ": process being destroyed" << processLog.endLog;
};

DarlingServer::Process::ID DarlingServer::Process::id() const {
	return _pid;
};

DarlingServer::Process::NSID DarlingServer::Process::nsid() const {
	return _nspid;
};

DarlingServer::EternalID DarlingServer::Process::eternalID() const {
	return _eid;
};

void DarlingServer::Process::_setEternalID(EternalID eid) {
	_eid = eid;
	_pidVersion = nextPIDVersion.fetch_add(1, std::memory_order_relaxed);
	dtape_task_set_process_generation(_dtapeTask, eid, _pidVersion);
	if (_responsibility.pid == 0) {
		_responsibility = {_nspid, _uniqueID, eid};
	}
};

std::vector<std::shared_ptr<DarlingServer::Thread>> DarlingServer::Process::threads() const {
	std::vector<std::shared_ptr<DarlingServer::Thread>> result;
	std::shared_lock lock(_rwlock);

	for (auto& [nsid, maybeThread]: _threads) {
		if (auto thread = maybeThread.lock()) {
			result.push_back(thread);
		}
	}

	return result;
};

std::string DarlingServer::Process::vchrootPath() const {
	std::shared_lock lock(_rwlock);
	return _cachedVchrootPath;
};

void DarlingServer::Process::setVchrootDirectory(std::shared_ptr<FD> directoryDescriptor) {
	std::unique_lock lock(_rwlock);
	_vchrootDescriptor = directoryDescriptor;

	char* tmp = new char[4096];

	auto fdPath = "/proc/self/fd/" + std::to_string(_vchrootDescriptor->fd());
	auto len = readlink(fdPath.c_str(), tmp, 4095);

	if (len < 0) {
		throw std::system_error(errno, std::generic_category(), "readlink");
	}

	tmp[len] = '\0';

	_cachedVchrootPath = std::string(tmp);
	delete[] tmp;
};

std::shared_ptr<DarlingServer::Process> DarlingServer::Process::currentProcess() {
	auto thread = Thread::currentThread();
	if (!thread) {
		return nullptr;
	}

	return thread->process();
};

std::shared_ptr<DarlingServer::Process> DarlingServer::Process::parentProcess() const {
	return _parentProcess.lock();
};

std::shared_ptr<DarlingServer::Process> DarlingServer::Process::kernelProcess() {
	static std::shared_ptr<Process> process = [&]() {
		auto proc = std::make_shared<Process>(KernelProcessConstructorTag());
		processRegistry().registerEntry(proc, true);
		return proc;
	}();
	return process;
};

bool DarlingServer::Process::startSuspended() const {
	std::shared_lock lock(_rwlock);
	return _startSuspended;
};

void DarlingServer::Process::setStartSuspended(bool startSuspended) {
	std::unique_lock lock(_rwlock);
	_startSuspended = startSuspended;
};

bool DarlingServer::Process::_readOrWriteMemory(bool isWrite, uintptr_t remoteAddress, void* localBuffer, size_t length, int* errorCode) const {
	struct iovec local;
	struct iovec remote;
	const auto func = isWrite ? process_vm_writev : process_vm_readv;
	static DarlingServer::Log processMemoryAccessLog("procmem");

	if (isDead()) {
		processMemoryAccessLog.error()
			<< "Failed to "
			<< (isWrite ? "write " : "read ")
			<< length
			<< " byte(s) at 0x"
			<< std::hex << remoteAddress << std::dec
			<< " in process "
			<< id()
			<< " ("
			<< nsid()
			<< "): process dead"
			<< processMemoryAccessLog.endLog;
		if (errorCode) {
			*errorCode = ESRCH;
		}
		return false;
	}

	local.iov_base = localBuffer;
	local.iov_len = length;

	remote.iov_base = (void*)remoteAddress;
	remote.iov_len = length;

	if (func(id(), &local, 1, &remote, 1, 0) < 0) {
		int code = errno;
		processMemoryAccessLog.error()
			<< "Failed to "
			<< (isWrite ? "write " : "read ")
			<< length
			<< " byte(s) at 0x"
			<< std::hex << remoteAddress << std::dec
			<< " in process "
			<< id()
			<< " ("
			<< nsid()
			<< "): "
			<< code
			<< " ("
			<< strerror(code)
			<< ")"
			<< processMemoryAccessLog.endLog;
		if (errorCode) {
			*errorCode = code;
		}
		return false;
	} else {
		processMemoryAccessLog.debug()
			<< "Successfully "
			<< (isWrite ? "wrote " : "read ")
			<< length
			<< " byte(s) at 0x"
			<< std::hex << remoteAddress << std::dec
			<< " in process "
			<< id()
			<< " ("
			<< nsid()
			<< ")"
			<< processMemoryAccessLog.endLog;
		if (errorCode) {
			*errorCode = 0;
		}
		return true;
	}
};

bool DarlingServer::Process::readMemory(uintptr_t remoteAddress, void* localBuffer, size_t length, int* errorCode) const {
	return _readOrWriteMemory(false, remoteAddress, localBuffer, length, errorCode);
};

bool DarlingServer::Process::writeMemory(uintptr_t remoteAddress, const void* localBuffer, size_t length, int* errorCode) const {
	// the const_cast is safe; when writing to a process' memory, localBuffer is not modified
	return _readOrWriteMemory(true, remoteAddress, const_cast<void*>(localBuffer), length, errorCode);
};

void DarlingServer::Process::notifyCheckin(Architecture architecture, bool isFork) {
	std::unique_lock lock(_rwlock);

	// The new mldr can check in before epoll dispatches the old image's exec
	// pipe event. Consume that same close-on-exec result before reading the flag.
	auto execResult = _completeExecListenerLocked(_execListener);
	if (execResult == ExecListenerResult::NotReady) {
		throw std::system_error(EAGAIN, std::generic_category(), "Exec listener is not complete at main-thread checkin");
	}
	if (execResult == ExecListenerResult::NativeExec) {
		lock.unlock();
		notifyDead();
		throw std::system_error(ESRCH, std::generic_category(), "Native exec cannot check in as a Darling process");
	}

	bool didExec = _pendingReplacement;

	if (didExec) {
		// exec case

		processLog.info() << *this << ": replacing process with a new task (with architecture \"" << architectureToString(architecture) << "\")" << processLog.endLog;

		// clear all threads except the main thread
		std::shared_ptr<Thread> mainThread = nullptr;
		while (!_threads.empty()) {
			auto it = _threads.begin();
			auto thread = it->second.lock();
			lock.unlock();
			if (thread) {
				if (thread->_nstid == _nspid) {
					mainThread = thread;
				} else {
					thread->_process = nullptr;
					thread->notifyDead();
				}
			}
			lock.lock();
			_threads.erase(it);
		}
		if (!mainThread) {
			throw std::runtime_error("Main thread for process died?");
		}
		_threads[mainThread->nsid()] = mainThread;

		// update the process architecture
		_architecture = architecture;

		// replace the old task with a new task that inherits from it
		auto oldTask = _dtapeTask;
		auto newTask = dtape_task_create(oldTask, _nspid, this, static_cast<dserver_rpc_architecture_t>(_architecture));
		_dtapeTask = newTask;
		_quarantineKernelCapabilities = 0;
		_pidVersion = nextPIDVersion.fetch_add(1, std::memory_order_relaxed);
		dtape_task_set_process_generation(_dtapeTask, _eid, _pidVersion);

		// now replace the main thread's duct-taped thread with a new one
		auto oldThread = mainThread->_dtapeThread;
		auto newThread = dtape_thread_create(_dtapeTask, mainThread->_nstid, mainThread.get());
		mainThread->_dtapeThread = newThread;

		// destroy the main thread's old S2C semaphores
		dtape_semaphore_destroy(mainThread->_s2cPerformSempahore);
		mainThread->_s2cPerformSempahore = nullptr;
		dtape_semaphore_destroy(mainThread->_s2cReplySempahore);
		mainThread->_s2cReplySempahore = nullptr;
		dtape_semaphore_destroy(mainThread->_s2cInterruptEnterSemaphore);
		mainThread->_s2cInterruptEnterSemaphore = nullptr;
		dtape_semaphore_destroy(mainThread->_s2cInterruptExitSemaphore);
		mainThread->_s2cInterruptExitSemaphore = nullptr;

		// destroy the fork-wait semaphore
		dtape_semaphore_destroy(_dtapeForkWaitSemaphore);
		_dtapeForkWaitSemaphore = nullptr;

		// release the main thread's old duct-taped thread
		dtape_thread_release(oldThread);

		// release the old task
		dtape_task_release(oldTask);

		// create a new fork-wait semaphore for the new task
		_dtapeForkWaitSemaphore = dtape_semaphore_create(_dtapeTask, 0);

		// create new S2C semaphores for the main thread
		mainThread->_s2cPerformSempahore = dtape_semaphore_create(_dtapeTask, 1);
		mainThread->_s2cReplySempahore = dtape_semaphore_create(_dtapeTask, 0);
		mainThread->_s2cInterruptEnterSemaphore = dtape_semaphore_create(_dtapeTask, 0);
		mainThread->_s2cInterruptExitSemaphore = dtape_semaphore_create(_dtapeTask, 0);
	} else {
		// fork case

		if (architecture != _architecture) {
			throw std::runtime_error("Impossible: parent process architecture != child process architecture on fork");
		}
	}

	_pendingReplacement = false;

	lock.unlock();

	if (didExec) {
		// notify listeners that we have exec'd (i.e. been replaced)
		_notifyListeningKqchannels(NOTE_EXEC, 0);
	} else if (isFork) {
		// notify the parent process (if we have one) that we've arrived
		if (auto parent = _parentProcess.lock()) {
			dtape_semaphore_up(parent->_dtapeForkWaitSemaphore);
			parent->_notifyListeningKqchannels(NOTE_FORK, nsid());
		}
	}
};

DarlingServer::Process::ExecListenerResult DarlingServer::Process::_completeExecListenerLocked(const std::shared_ptr<FD>& expected) {
	// A late callback for a pipe already consumed by checkin must not mark the
	// replacement pending again (or consume a subsequent exec's pipe).
	if (!expected || _execListener != expected) {
		return ExecListenerResult::Completed;
	}
	if (_dead) {
		_execListener.reset();
		return ExecListenerResult::Completed;
	}

	char failure;
	ssize_t result;
	do {
		result = read(expected->fd(), &failure, sizeof(failure));
	} while (result < 0 && errno == EINTR);
	if (result < 0) {
		if (errno == EAGAIN || errno == EWOULDBLOCK) {
			return ExecListenerResult::NotReady;
		}
		throw std::system_error(errno, std::generic_category(), "Failed to read from exec listener pipe");
	}

	auto completed = ExecListenerResult::Completed;
	if (result == 0) {
		if (_execListenerExecutingMacho) {
			_setPendingReplacementLocked(_execListenerDisclaim);
		} else {
			completed = ExecListenerResult::NativeExec;
		}
	}
	// A failure byte leaves the old task and responsibility untouched.
	_execListener.reset();
	return completed;
};

void DarlingServer::Process::setExecListener(std::shared_ptr<FD> listener, bool executingMacho, bool disclaim) {
	std::unique_lock lock(_rwlock);
	if (_dead) {
		throw std::system_error(ESRCH, std::generic_category(), "Cannot register exec for a dead process");
	}
	// A failed exec can be followed immediately by another checkout before its
	// monitor runs. Finish the ready old pipe without replacing an in-flight one.
	auto previous = _completeExecListenerLocked(_execListener);
	if (previous == ExecListenerResult::NotReady) {
		throw std::system_error(EBUSY, std::generic_category(), "Previous exec listener is still pending");
	}
	if (previous == ExecListenerResult::NativeExec) {
		lock.unlock();
		notifyDead();
		throw std::system_error(ESRCH, std::generic_category(), "Process completed a native exec");
	}
	_execListener = std::move(listener);
	_execListenerExecutingMacho = executingMacho;
	_execListenerDisclaim = disclaim;
};

bool DarlingServer::Process::completeExecListener(const std::shared_ptr<FD>& expected) {
	std::unique_lock lock(_rwlock);
	auto result = _completeExecListenerLocked(expected);
	lock.unlock();
	if (result == ExecListenerResult::NativeExec) {
		notifyDead();
	}
	return result != ExecListenerResult::NotReady;
};

void DarlingServer::Process::_setPendingReplacementLocked(bool disclaim) {
	processLog.info() << "Process " << id() << " (" << nsid() << ") is now pending replacement" << processLog.endLog;

	_pendingReplacement = true;
	if (disclaim) {
		// The close-on-exec pipe has confirmed a successful exec. Failed execs
		// never arrive here and cannot change the old process's responsibility.
		_responsibility = {_nspid, _uniqueID, _eid};
	}
};

void DarlingServer::Process::setPendingReplacement(bool disclaim) {
	std::unique_lock lock(_rwlock);
	_setPendingReplacementLocked(disclaim);
};

DarlingServer::Process::Responsibility DarlingServer::Process::responsibility() const {
	std::shared_lock lock(_rwlock);
	return _responsibility;
};

void DarlingServer::Process::registerKqchan(std::shared_ptr<Kqchan> kqchan) {
	std::unique_lock lock(_rwlock);

	_kqchannels[kqchan->_idForProcess()] = kqchan;
};

void DarlingServer::Process::unregisterKqchan(std::shared_ptr<Kqchan> kqchan) {
	std::unique_lock lock(_rwlock);

	_kqchannels.erase(kqchan->_idForProcess());
};

void DarlingServer::Process::waitForChildAfterFork() {
	// this function is always called within a microthread
	dtape_semaphore_down_simple(_dtapeForkWaitSemaphore);
};

void DarlingServer::Process::registerListeningKqchan(std::shared_ptr<Kqchan::Process> kqchan) {
	std::unique_lock lock(_rwlock);
	uintptr_t id = static_cast<std::shared_ptr<Kqchan>>(kqchan)->_idForProcess();
	_listeningKqchannels[id] = kqchan;
};

void DarlingServer::Process::unregisterListeningKqchan(uintptr_t kqchanID) {
	std::unique_lock lock(_rwlock);
	_listeningKqchannels.erase(kqchanID);
};

void DarlingServer::Process::_notifyListeningKqchannels(uint32_t event, int64_t data) {
	decltype(_listeningKqchannels) listeningKqchannels;

	// we do NOT want to be holding our rwlock when we notify the kqchannels; that can lead to deadlocks
	{
		std::shared_lock lock(_rwlock);
		listeningKqchannels = _listeningKqchannels;
	}

	for (auto& [id, maybeKqchan]: listeningKqchannels) {
		auto kqchan = maybeKqchan.lock();

		if (!kqchan) {
			continue;
		}

		kqchan->_notify(event, data);
	}
};

bool DarlingServer::Process::is64Bit() const {
	return _architecture == Architecture::x86_64 || _architecture == Architecture::ARM64;
};

DarlingServer::Process::Architecture DarlingServer::Process::architecture() const {
	return _architecture;
};

void DarlingServer::Process::logToStream(Log::Stream& stream) const {
	stream << "[P:" << _pid << "(" << _nspid << ")]";
};

DarlingServer::Process::MemoryInfo DarlingServer::Process::memoryInfo() const {
	if (isDead()) {
		throw std::system_error(ESRCH, std::generic_category(), "dead process; can't call memoryInfo");
	}

	MemoryInfo info;
	std::ifstream file("/proc/" + std::to_string(_pid) + "/statm");

	file >> info.virtualSize >> info.residentSize;

	info.virtualSize *= sysconf(_SC_PAGESIZE);
	info.residentSize *= sysconf(_SC_PAGESIZE);

	// CHECKME: can different processes have different page sizes on Linux?
	info.pageSize = sysconf(_SC_PAGESIZE);

	// TODO
	info.regionCount = 0;

	return info;
};

std::vector<DarlingServer::Process::MemoryRegionInfo> DarlingServer::Process::memoryRegions() const {
	if (isDead()) throw std::system_error(ESRCH, std::generic_category(), "dead process; can't read maps");
	std::ifstream file("/proc/" + std::to_string(_pid) + "/maps");
	if (!file) throw std::system_error(EIO, std::generic_category(), "cannot open process maps");
	std::vector<MemoryRegionInfo> regions;
	std::string line;
	uint64_t previousEnd = 0;
	uint64_t pageSize = sysconf(_SC_PAGESIZE);
	while (std::getline(file, line)) {
		ProcMaps::Entry entry;
		if (!ProcMaps::parse(line, entry) || entry.start < previousEnd
				|| entry.start % pageSize || entry.end % pageSize)
			throw std::system_error(EIO, std::generic_category(), "malformed process maps entry");
		MemoryRegionInfo info;
		info.startAddress = entry.start;
		info.pageCount = (entry.end - entry.start) / pageSize;
		info.mapOffset = entry.offset;
		info.fileDevice = entry.device;
		info.fileInode = entry.inode;
		info.protection = entry.protection;
		info.shared = entry.shared;
		regions.push_back(info);
		previousEnd = entry.end;
	}
	if (file.bad()) throw std::system_error(EIO, std::generic_category(), "cannot read process maps");
	return regions;
};

DarlingServer::Process::MemoryRegionInfo DarlingServer::Process::memoryRegionInfo(uintptr_t address) const {
	for (const auto& info : memoryRegions()) {
		if (info.startAddress > address) break;
		if (address - info.startAddress < info.pageCount * sysconf(_SC_PAGESIZE)) return info;
	}
	throw std::system_error(EFAULT, std::generic_category(), "address not mapped");
};

#if DSERVER_EXTENDED_DEBUG

void DarlingServer::Process::_registerName(uint32_t name, uintptr_t pointer) {
	std::unique_lock lock(_rwlock);
	_registeredNames[name] = pointer;
};

void DarlingServer::Process::_unregisterName(uint32_t name) {
	std::unique_lock lock(_rwlock);
	_registeredNames.erase(name);
};

void DarlingServer::Process::_addPortSetMember(dtape_port_set_id_t portSetID, dtape_port_id_t portID) {
	std::unique_lock lock(_rwlock);
	auto& members = _portSetMembers[portSetID];
	members.insert(portID);
};

void DarlingServer::Process::_removePortSetMember(dtape_port_set_id_t portSetID, dtape_port_id_t portID) {
	std::unique_lock lock(_rwlock);
	if (_portSetMembers.find(portSetID) != _portSetMembers.end()) {
		auto& members = _portSetMembers[portSetID];
		members.erase(portID);
		if (members.empty()) {
			_portSetMembers.erase(portSetID);
		}
	}
};

void DarlingServer::Process::_clearPortSet(dtape_port_set_id_t portSetID) {
	std::unique_lock lock(_rwlock);
	_portSetMembers.erase(portSetID);
};

#endif

std::shared_ptr<DarlingServer::Process> DarlingServer::Process::tracerProcess() const {
	std::shared_lock lock(_rwlock);
	return _tracerProcess.lock();
};

bool DarlingServer::Process::setTracerProcess(std::shared_ptr<Process> tracerProcess) {
	std::unique_lock lock(_rwlock);
	if (!_tracerProcess.expired()) {
		return false;
	}
	_tracerProcess = tracerProcess;
	return true;
};

std::shared_ptr<DarlingServer::Thread> DarlingServer::Process::_pickS2CThread(void) const {
	if (isDead()) {
		return nullptr;
	}

	// if we're the process for the current thread (i.e. we're the current process), use the current thread
	if (currentProcess().get() == this) {
		return Thread::currentThread();
	}

	// Thread objects can outlive their Linux thread while an interrupted call
	// unwinds. A successful weak_ptr::lock() does not prove that the thread can
	// receive an S2C request. Snapshot the candidates without nesting the process
	// lock with their individual locks (or their destructors).
	std::vector<std::shared_ptr<Thread>> candidates;
	{
		std::shared_lock lock(_rwlock);
		for (auto& [id, weakThread]: _threads) {
			if (auto thread = weakThread.lock()) candidates.push_back(std::move(thread));
		}
	}
	std::shared_ptr<Thread> fallback;
	for (auto& thread: candidates) {
		if (thread->isDead()) continue;
		// A thread already waiting for a server reply needs no signal roundtrip.
		if (thread->activeCall()) return thread;
		if (!fallback) fallback = thread;
	}
	return fallback;
};

std::string DarlingServer::Process::executablePath() const {
	std::shared_lock lock(_rwlock);
	return _executablePath;
};

void DarlingServer::Process::setExecutablePath(std::string path) {
	std::unique_lock lock(_rwlock);
	_executablePath = std::move(path);
};

uintptr_t DarlingServer::Process::allocatePages(size_t pageCount, int protection, uintptr_t addressHint, bool fixed, bool overwrite) {
	auto thread = _pickS2CThread();

	if (!thread) {
		throw std::system_error(ESRCH, std::generic_category());
	}

	return thread->allocatePages(pageCount, protection, addressHint, fixed, overwrite);
};

void DarlingServer::Process::freePages(uintptr_t address, size_t pageCount) {
	auto thread = _pickS2CThread();

	if (!thread) {
		throw std::system_error(ESRCH, std::generic_category());
	}

	return thread->freePages(address, pageCount);
};

uintptr_t DarlingServer::Process::mapFile(int fd, size_t pageCount, int protection, uintptr_t addressHint, size_t pageOffset, bool fixed, bool overwrite) {
	auto thread = _pickS2CThread();

	if (!thread) {
		throw std::system_error(ESRCH, std::generic_category());
	}

	return thread->mapFile(fd, pageCount, protection, addressHint, pageOffset, fixed, overwrite);
};

void DarlingServer::Process::changeProtection(uintptr_t address, size_t pageCount, int protection) {
	auto thread = _pickS2CThread();

	if (!thread) {
		throw std::system_error(ESRCH, std::generic_category());
	}

	return thread->changeProtection(address, pageCount, protection);
};

void DarlingServer::Process::syncMemory(uintptr_t address, size_t size, int sync_flags) {
	auto thread = _pickS2CThread();

	if (!thread) {
		throw std::system_error(ESRCH, std::generic_category());
	}

	return thread->syncMemory(address, size, sync_flags);
};

uintptr_t DarlingServer::Process::getNextRegion(uintptr_t address) const {
	for (const auto& info : memoryRegions()) {
		if (info.startAddress > address) return info.startAddress;
	}
	return 0;
};

void DarlingServer::Process::notifyDead() {
	decltype(_threads) threads;
	{
		std::unique_lock lock(_rwlock);
		if (_dead) {
			return;
		}

		processLog.info() << *this << ": process dying" << processLog.endLog;
		_dead = true;
		threads = _threads;

		// clear out all kqchannels we own
		_kqchannels.clear();
	}

	// keep ourselves alive until the duct-taped context is done
	_selfReference = shared_from_this();

	// TODO: get exit status
	_notifyListeningKqchannels(NOTE_EXIT, 0);

	dtape_task_dying(_dtapeTask);

	// notify all our threads that we're dead
	for (auto [id, maybeThread]: threads) {
		auto thread = maybeThread.lock();
		if (!thread) {
			continue;
		}
		thread->notifyDead();
	}

	// schedule the duct-taped task to be released
	// dtape_thread_release needs a microthread context, so we call it within a kernel microthread
	// also destroy the fork-wait semaphore here
	Thread::kernelAsync([self = shared_from_this()]() {
		if (self->_dtapeForkWaitSemaphore) {
			dtape_semaphore_destroy(self->_dtapeForkWaitSemaphore);
			self->_dtapeForkWaitSemaphore = nullptr;
		}
		dtape_task_release(self->_dtapeTask);
		self->_dtapeTask = nullptr;
	});

	processRegistry().unregisterEntry(shared_from_this());
};

void DarlingServer::Process::_dispose() {
	_selfReference = nullptr;
};

bool DarlingServer::Process::isDead() const {
	std::shared_lock lock(_rwlock);
	return _dead;
};

std::vector<uint32_t> DarlingServer::Process::groups() const {
	std::shared_lock lock(_rwlock);
	return _groups;
};

void DarlingServer::Process::setGroups(const std::vector<uint32_t>& groups) {
	std::unique_lock lock(_rwlock);
	_groups = groups;
};
