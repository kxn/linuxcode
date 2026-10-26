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

#define _GNU_SOURCE 1
#include <darlingserver/call.hpp>
#include <darlingserver/server.hpp>
#include <sys/uio.h>
#include <cstring>
#include <fstream>
#include <sstream>

#include <darlingserver/logging.hpp>
#include <darlingserver/duct-tape.h>
#include <darlingserver/config.hpp>
#include <sys/fcntl.h>
#include <sys/syscall.h>
#include <darlingserver/kqchan.hpp>
#include <darlingserver/sandbox-policy.hpp>
#include <darlingserver/fsevents-device.hpp>
#include <darlingserver/file-signatures.hpp>

static DarlingServer::Log callLog("calls");

DarlingServer::Log DarlingServer::Call::rpcReplyLog("replies");

std::shared_ptr<DarlingServer::Call> DarlingServer::Call::callFromMessage(Message&& requestMessage) {
	if (requestMessage.data().size() < sizeof(dserver_rpc_callhdr_t)) {
		throw std::invalid_argument("Message buffer was too small for call header");
	}

	dserver_rpc_callhdr_t* header = reinterpret_cast<dserver_rpc_callhdr_t*>(requestMessage.data().data());
	std::shared_ptr<Call> result = nullptr;
	std::shared_ptr<Process> process = nullptr;
	std::shared_ptr<Thread> thread = nullptr;

	// first, make sure we know this call number
	switch (header->number) {
		case dserver_callnum_s2c:
		case dserver_callnum_push_reply:
		DSERVER_VALID_CALLNUM_CASES
			break;

		default:
			throw std::invalid_argument("Invalid call number");
	}

	if ((header->number & DSERVER_CALL_UNMANAGED_FLAG) == 0) {
		// now let's lookup (and possibly create) the process and thread making this call
		process = processRegistry().registerIfAbsent(header->pid, [&]() {
			std::shared_ptr<Process> tmp = nullptr;

			int lifetimePipe = -1;

			if (header->number == dserver_callnum_checkin) {
				auto checkinCall = reinterpret_cast<dserver_rpc_call_checkin_t*>(header);
				if (checkinCall->body.lifetime_listener_pipe != -1) {
					lifetimePipe = requestMessage.extractDescriptorAtIndex(checkinCall->body.lifetime_listener_pipe);
					checkinCall->body.lifetime_listener_pipe = -1;
				}
			}

			try {
				tmp = std::make_shared<Process>(requestMessage.pid(), header->pid, static_cast<Process::Architecture>(header->architecture), lifetimePipe);
			} catch (std::system_error e) {
				return tmp;
			}

			Server::sharedInstance().monitorProcess(tmp);
			return tmp;
		});

		if (!process) {
			callLog.error() << "Received call from non-existent process?" << callLog.endLog;

			// ignore this call
			// TODO: instead of ignoring it, we should return a generic reply indicating `-ESRCH` or something like that.
			return nullptr;
		}

		thread = threadRegistry().registerIfAbsent(header->tid, [&]() {
			std::shared_ptr<Thread> tmp = nullptr;

			void* stackHint = nullptr;

			if (header->number == dserver_callnum_checkin) {
				auto checkinCall = reinterpret_cast<dserver_rpc_call_checkin_t*>(header);
				stackHint = reinterpret_cast<void*>(checkinCall->body.stack_hint);
			}

			try {
				tmp = std::make_shared<Thread>(process, header->tid, stackHint);
			} catch (std::system_error e) {
				return tmp;
			}

			tmp->setAddress(requestMessage.address());
			tmp->registerWithProcess();
			return tmp;
		});

		if (!thread) {
			callLog.error() << "Received call from non-existent thread?" << callLog.endLog;

			// ignore this call
			// TODO: instead of ignoring it, we should return a generic reply indicating `-ESRCH` or something like that.
			return nullptr;
		}

		thread->setAddress(requestMessage.address());

		if (process->id() != requestMessage.pid()) {
			throw std::runtime_error("System-reported message PID != darlingserver-recorded PID");
		}
	}

	auto pidString = (process) ? (std::to_string(process->id()) + " (" + std::to_string(process->nsid()) + ")") : (std::to_string(header->pid) + " (-1)");
	auto tidString = (thread) ? (std::to_string(thread->id()) + " (" + std::to_string(thread->nsid()) + ")") : (std::to_string(header->tid) + " (-1)");
	callLog.debug() << "Received call #" << header->number << " (" << dserver_callnum_to_string(header->number) << ") from PID " << pidString << ", TID " << tidString << callLog.endLog;

	if (header->number == dserver_callnum_s2c) {
		// this is an S2C reply

		{
			std::unique_lock lock(thread->_rwlock);

			if (thread->_s2cReply) {
				throw std::runtime_error("Received S2C reply but thread already had one pending");
			}

			thread->_s2cReply = std::move(requestMessage);
		}

		dtape_semaphore_up(thread->_s2cReplySempahore);

		return nullptr;
	} else if (header->number == dserver_callnum_push_reply) {
		// this is a reply push
		// (used to send interrupted replies back to the server)

		auto pushReplyCall = reinterpret_cast<const dserver_rpc_call_push_reply_t*>(requestMessage.data().data());
		Message replyToSave(pushReplyCall->reply_size, 0);

		// extract the reply-push synchronization pipe
		auto pipeDesc = requestMessage.extractDescriptorAtIndex(requestMessage.descriptors().size() - 1);
		char tmp = 1;

		if (pipeDesc < 0) {
			throw std::runtime_error("Failed to extract reply-push synchronization pipe");
		}

		if (!process->readMemory(pushReplyCall->reply, replyToSave.data().data(), pushReplyCall->reply_size)) {
			throw std::runtime_error("Failed to read client-pushed reply body");
		}

		replyToSave.replaceDescriptors(requestMessage.descriptors());
		requestMessage.replaceDescriptors({});

		replyToSave.setAddress(requestMessage.address());

		{
			std::unique_lock lock(thread->_rwlock);
			if (thread->_pendingCall && thread->_pendingCall->number() == Call::Number::InterruptEnter) {
				// this means the client got interrupted after we had already sent a reply for the interrupted call,
				// the client saw this unexpected reply while waiting for interrupt_enter to respond and sent it back to us,
				// and we received both calls (interrupt_enter and push_reply) at the same time
				thread->_pendingSavedReply = std::move(replyToSave);
			} else {
				if (thread->_interrupts.empty()) {
					throw std::runtime_error("Client tried to push reply outside of interrupt");
				}
				if (thread->_interrupts.top().savedReply) {
					throw std::runtime_error("Client-pushed reply overwriting existing saved reply");
				}
				thread->_interrupts.top().savedReply = std::move(replyToSave);
			}
		}

		callLog.debug() << *thread << ": Saved client-pushed reply (" << ((thread->_pendingSavedReply) ? "pending" : "normal") << ")" << callLog.endLog;

		// write a byte to the pipe so the caller can continue
		write(pipeDesc, &tmp, sizeof(tmp));
		// and close it
		close(pipeDesc);

		return nullptr;
	}

	// finally, let's construct the call class

	#define CALL_CASE(_callName, _className) \
		case dserver_callnum_ ## _callName: { \
			if (requestMessage.data().size() < sizeof(dserver_rpc_call_ ## _callName ## _t)) { \
				throw std::invalid_argument("Message buffer was too small for dserver_call_" #_callName "_t"); \
			} \
			result = std::make_shared<_className>(thread, reinterpret_cast<dserver_rpc_call_ ## _callName ## _t*>(header), std::move(requestMessage)); \
		} break;

	switch (header->number) {
		DSERVER_CONSTRUCT_CASES

		default:
			throw std::invalid_argument("Invalid call number");
	}

	#undef CALL_CASE

	if (thread) {
		thread->setPendingCall(result);
		return result;
	} else {
		Thread::kernelAsync([result]() {
			result->processCall();
		});
		return nullptr;
	}
};

DarlingServer::Call::Call(std::shared_ptr<Thread> thread, Address replyAddress, dserver_rpc_callhdr_t* callHeader):
	_thread(thread),
	_replyAddress(replyAddress),
	_header(*callHeader)
	{};

DarlingServer::Call::~Call() {};

std::shared_ptr<DarlingServer::Thread> DarlingServer::Call::thread() const {
	return _thread.lock();
};

void DarlingServer::Call::sendBasicReply(int resultCode) {
	throw std::runtime_error("This call cannot send a basic reply");
};

void DarlingServer::Call::sendBSDReply(int resultCode, uint32_t returnValue) {
	throw std::runtime_error("This call cannot send a BSD reply");
};

bool DarlingServer::Call::isXNUTrap() const {
	return false;
};

bool DarlingServer::Call::isBSDTrap() const {
	return false;
};

void DarlingServer::Call::sendReply(Message&& reply) {
	Server::sharedInstance().sendMessage(std::move(reply));
};

//
// call processing
//

/*
 *
 * A note about RPC wrappers:
 *
 * The auto-generated RPC wrappers provide both client-side wrappers as well as server-side wrappers.
 * The server-side wrappers automatically handle a few things like replies and descriptors.
 *
 * Replies:
 * The RPC wrappers provide a custom `_sendReply` method specific to each call class.
 * This method takes the result/status code as its first parameter followed by the return parameters
 * specified in the call interface. When a call is done processing, it simply calls `_sendReply` with the necessary
 * parameters and the RPC wrappers will take care of setting up the message and loading it onto the reply queue
 * for the server to send it out.
 *
 * Descriptors:
 * The RPC wrappers automatically handle ownership of descriptors, both incoming and outgoing.
 *
 * Incoming descriptors are extracted from the message and ownership is moved into the call instance.
 * The call processing code can use the descriptor however it likes while the call instance is still alive.
 * If it would like to move ownership out of the call instance, it can set the descriptor in the `_body` to `-1`.
 * Descriptors still left in the `_body` when the call instance is destroyed are automatically closed.
 *
 * Ownership of outgoing descriptors is passed into the reply message. In other words, when a descriptor
 * is given to `_sendReply`, the call instance loses ownership of that descriptor. If the call instance
 * would like to retain ownership, it should `dup()` the descriptor and pass the `dup()`ed descriptor to `_sendReply` instead.
 *
 */

void DarlingServer::Call::Checkin::processCall() {
	// the Call instance creation already took care of registering the process and thread.

	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			// the process needs to know when the checkin occurs, in case it has a pending replacement
			// and also to notify its parent about when the fork is complete
			process->notifyCheckin(static_cast<Process::Architecture>(_header.architecture));
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

int DarlingServer::Call::_checkout(int& execListener, bool executingMacho, bool disclaim) {
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			if (execListener >= 0) {
				// this is actually an execve;
				// let's monitor the FD we got

				// make it non-blocking
				int flags = fcntl(execListener, F_GETFL);
				if (flags < 0) {
					code = -errno;
				} else {
					flags |= O_NONBLOCK;
					if (fcntl(execListener, F_SETFL, flags) < 0) {
						code = -errno;
					} else {
						// now monitor it
						auto fd = std::make_shared<FD>(execListener);
						execListener = -1; // the FD instance now owns the descriptor

						auto replacingWithDarlingProcess = executingMacho;

						std::weak_ptr<Process> weakProcess = process;
						Server::sharedInstance().addMonitor(std::make_shared<Monitor>(fd, Monitor::Event::HangUp, false, true, [fd, weakProcess, replacingWithDarlingProcess, disclaim](std::shared_ptr<Monitor> monitor, Monitor::Event events) {
							Server::sharedInstance().removeMonitor(monitor);

							auto process = weakProcess.lock();

							if (!process) {
								// the process died...
								return;
							}

							char tmp;
							int result = read(fd->fd(), &tmp, sizeof(tmp));

							if (result < 0) {
								// we shouldn't even get EAGAIN
								throw std::system_error(errno, std::generic_category(), "Failed to read from exec listener pipe");
							}

							if (result == 0) {
								// the execve succeeded
								if (replacingWithDarlingProcess) {
									process->setPendingReplacement(disclaim);
								} else {
									// the Darling process was replaced with a non-Darling process
									// treat it like death
									process->notifyDead();
								}
							} else {
								// the execve failed
								// do nothing in this case
							}
						}));
					}
				}
			} else {
				thread->notifyDead();

				// if this was the last thread in the process, it'll be automatically unregistered
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	// clear the thread pointer so that the reply will be sent directly through the server
	// (otherwise, we would attempt to send it through the thread, which is now dead)
	_thread.reset();

	return code;
};

void DarlingServer::Call::Checkout::processCall() {
    int code = _checkout(_body.exec_listener_pipe, _body.executing_macho, false);
    _sendReply(code);
};

void DarlingServer::Call::CheckoutDisclaim::processCall() {
    int code = _checkout(_body.exec_listener_pipe, _body.executing_macho, true);
    _sendReply(code);
};

void DarlingServer::Call::QuarantineKernelReady::processCall() {
    int code = -ESRCH;
    auto thread = _thread.lock();
    auto process = thread ? thread->process() : nullptr;
    if (process) {
        if (_body.capabilities != 0x0001000f) code = -EINVAL;
        else {
            std::unique_lock lock(process->_rwlock);
            process->_quarantineKernelCapabilities = _body.capabilities;
            code = 0;
        }
    }
    _sendReply(code);
};

void DarlingServer::Call::ProcessGetGeneration::processCall() {
    int code = -ESRCH;
    uint32_t generation = 0;
    auto thread = _thread.lock();
    auto process = thread ? thread->process() : nullptr;
    if (process) {
        if (_body.pid <= 0) code = -EINVAL;
        else {
            auto entry = processRegistry().lookupEntryByNSID(_body.pid);
            auto target = entry ? *entry : nullptr;
            if (target && !target->isDead()) {
                std::shared_lock lock(target->_rwlock);
                generation = target->_pidVersion;
                code = 0;
            }
        }
    }
    _sendReply(code, generation);
};

void DarlingServer::Call::MacSyscall::processCall() {
    int code = -ESRCH;
    auto thread = _thread.lock();
    auto process = thread ? thread->process() : nullptr;
    if (process) {
        std::string policy;
        char ch = 0;
        code = 0;
        for (size_t i = 0; i < 32; ++i) {
            if (!process->readMemory(_body.policy + i, &ch, 1)) { code = -EFAULT; break; }
            if (!ch) break;
            policy += ch;
        }
        // Preserve Darwin policy errno separately from Linux RPC transport.
        if (!code && ch) code = -63; // ENAMETOOLONG
        if (!code && policy == "Sandbox") {
            if (_body.operation == 0) {
                // Pinned Intel sandbox_apply_container ABI: data, byte count,
                // optional container string, container string byte count.
                // Copy the upload once before parsing it; guest memory is not
                // stable across separate validation and execution passes.
                uint64_t upload[4] = {};
                if (!process->readMemory(_body.arguments, upload, sizeof(upload))) code = -EFAULT;
                if (!code && (upload[2] || upload[3])) code = -45; // containers not implemented
                if (!code && (!upload[1] || upload[1] > 1024 * 1024)) code = -EINVAL;
                if (!code && (!upload[0] || upload[0] > UINT64_MAX - upload[1])) code = -EFAULT;
                if (!code) {
                    std::vector<uint8_t> bytes(upload[1]);
                    if (!process->readMemory(upload[0], bytes.data(), bytes.size())) code = -EFAULT;
                    else {
                        std::string error;
                        auto decoded = Sandbox::Policy::parse(std::move(bytes), error);
                        if (!decoded) {
                            callLog.debug() << "Sandbox upload rejected: " << error;
                            code = -EINVAL;
                        } else if (decoded->allowsAllOperations()) {
                            std::unique_lock lock(process->_rwlock);
                            if (process->_sandboxState != Process::SandboxState::Unconfined) code = -EPERM;
                            else {
                                process->_sandboxPolicy = std::move(decoded);
                                process->_sandboxState = Process::SandboxState::UnrestrictedProfile;
                                callLog.info() << "Attached native Sandbox policy proven unrestricted for all operations";
                            }
                        } else {
                            callLog.error() << "Sandbox upload decoded: " << decoded->nodeCount()
                                << " nodes; attachment refused because operation enforcement is unavailable";
                            // Keep process state unchanged. A decoded graph is
                            // not a successfully applied Sandbox policy.
                            code = -45;
                        }
                    }
                }
                _sendReply(0, -code);
                return;
            }
            // Query actual process state. Restrictive policies, extensions,
            // approvals and target-credential POSIX access remain unsupported.
            if (_body.operation != 2) code = -45;
            uint64_t args[20] = {};
            if (!code && !process->readMemory(_body.arguments, args, sizeof(args))) code = -EFAULT;
            if (!code && !args[0]) code = -EFAULT;
            if (!code && args[1] > INT32_MAX) code = -EINVAL;
            if (!code && (args[5] & ~uint64_t(0x4000007b))) code = -EINVAL;
            if (!code && (args[5] & 0x60)) code = -45; // POSIX checks are not Sandbox state queries
            for (unsigned i = 7; !code && i < 20; ++i) if (args[i]) code = -EINVAL;
            if (!code && !(args[5] & 0x40000000) && args[6]) code = -EINVAL;
            auto target = process;
            if (!code && args[1]) {
                auto entry = processRegistry().lookupEntryByNSID(args[1]);
                target = entry ? *entry : nullptr;
            }
            if (!code && (!target || target->isDead())) code = -ESRCH;
            auto readString = [&](uintptr_t address, size_t limit, std::string& value) {
                for (size_t i = 0; i < limit; ++i) {
                    char byte;
                    if (!process->readMemory(address + i, &byte, 1)) return -EFAULT;
                    if (!byte) return 0;
                    value += byte;
                }
                return -63; // Darwin ENAMETOOLONG
            };
            std::string operation;
            if (!code && args[2]) {
                code = readString(args[2], 256, operation);
                if (!code && operation.empty()) code = -EINVAL;
            }
            bool scalar = false, compound = false, string = false;
            if (!code) {
                switch (args[3]) {
                    case 0: if (args[4]) code = -EINVAL; break;
                    case 240: case 65: case 75: case 52: scalar = true; break;
                    case 35: case 241: compound = true; break;
                    case 28: break; // descriptor value is opaque to an unconfined-state query
                    case 1: case 6: case 7: case 25: case 27:
                    case 33: case 34: case 50: case 19: case 45: case 5: case 69:
                        string = true; break;
                    default: code = -EINVAL;
                }
            }
            if (!code && scalar && args[4] > UINT32_MAX) code = -EINVAL;
            uint64_t pair[2] = {};
            if (!code && compound && !process->readMemory(args[4], pair, sizeof(pair))) code = -EFAULT;
            if (!code && compound && args[3] == 35) { args[4] = pair[0]; string = true; }
            std::string argument;
            if (!code && string) code = readString(args[4], 4096, argument);
            if (!code) {
                Process::SandboxState state;
                std::shared_ptr<const Sandbox::Policy> attached;
                {
                    std::shared_lock lock(target->_rwlock);
                    state = target->_sandboxState;
                    attached = target->_sandboxPolicy;
                    if ((args[5] & 0x40000000) && args[6] != target->_pidVersion) code = -ESRCH;
                }
                if (code) { _sendReply(0, -code); return; }
                if (state == Process::SandboxState::Unsupported) code = -45;
                else {
                    uint64_t decision = 0;
                    if (state == Process::SandboxState::UnrestrictedProfile) {
                        if (!attached || !attached->allowsAllOperations()) code = -45;
                        else if (!args[2]) decision = 1; // a real profile is attached
                        else if (attached->evaluate(operation, Sandbox::Context{}) != Sandbox::Decision::Allow) code = -EINVAL;
                    }
                    if (!code && !process->writeMemory(args[0], &decision, sizeof(decision))) code = -EFAULT;
                }
            }
        } else if (!code && policy == "Quarantine" && _body.operation == 87) {
            // Native nine-slot setprocinfo ABI. Only the actual flags-6 policy
            // implemented by the paired source VFS is supported here; do not
            // turn unknown approval/tracking/exclusion requests into success.
            uint64_t args[9] = {};
            if (!process->readMemory(_body.arguments, args, sizeof(args))) code = -EFAULT;
            if (!code && (!args[1] || args[2] > 1024 || args[5] > 2048 || args[7] > 2048 || args[8] > 0x1fff)) code = -EINVAL;
            if (!code && (args[0] || args[5] || args[6] || args[7] || args[8] != 6 || args[2] > 64)) code = -45;
            std::string identifier;
            if (!code) {
                for (size_t i = 0; i < 256; ++i) {
                    char byte;
                    if (!process->readMemory(args[1]+i, &byte, 1)) { code = -EFAULT; break; }
                    if (!byte) break;
                    identifier += byte;
                    if (i == 255) code = -63;
                }
            }
            std::vector<uint8_t> metadata;
            if (!code && args[2]) {
                metadata.resize(args[2]);
                if (!process->readMemory(args[3], metadata.data(), metadata.size())) code = -EFAULT;
            }
            if (!code) {
                std::unique_lock lock(process->_rwlock);
                if (process->_quarantineKernelCapabilities != 0x0001000f) code = -45;
                else if (process->_quarantineState &&
                    (process->_quarantineState->identifier != identifier || process->_quarantineState->metadata != metadata)) code = -45;
                else process->_quarantineState = std::make_shared<const Process::QuarantineState>(Process::QuarantineState{std::move(identifier), std::move(metadata), 6});
            }
        } else if (!code && policy == "Quarantine" && _body.operation == 84) {
            // Native getprocinfo writes lengths and flags back to its eight
            // argument slots, plus the three caller-provided output buffers.
            std::shared_ptr<const Process::QuarantineState> state;
            { std::shared_lock lock(process->_rwlock); state = process->_quarantineState; }
            if (!state) code = -93; // actual absent process Quarantine label
            uint64_t args[8] = {};
            if (!code && !process->readMemory(_body.arguments, args, sizeof(args))) code = -EFAULT;
            if (!code && (!args[1] || !args[3] || !args[5])) code = -EINVAL;
            if (!code) {
                args[0] = state->identifier.size(); args[2] = state->metadata.size(); args[4] = 0; args[6] = state->flags;
                if (!process->writeMemory(_body.arguments, args, sizeof(args))) code = -EFAULT;
                if (!code && args[0] && !process->writeMemory(args[1], state->identifier.data(), args[0])) code = -EFAULT;
                if (!code && args[2] && !process->writeMemory(args[3], state->metadata.data(), args[2])) code = -EFAULT;
            }
        } else if (!code && policy != "Quarantine") code = -103; // ENOPOLICY
        else if (!code && _body.operation != 180) code = -45; // ENOTSUP
        else if (!code) {
            // The native libquarantine query SPI passes five 64-bit slots:
            // pid, optional pid output, optional unique-ID output, reserved x2.
            uint64_t args[5];
            if (!process->readMemory(_body.arguments, args, sizeof(args))) code = -EFAULT;
            else if (args[0] > INT32_MAX) code = -EINVAL;
            else if (args[3] || args[4]) code = -45;
            else {
                auto target = process;
                if (args[0]) {
                    auto entry = processRegistry().lookupEntryByNSID(args[0]);
                    target = entry ? *entry : nullptr;
                }
                if (!target || target->isDead()) code = -ESRCH;
                else {
                    auto info = target->responsibility();
                    if (args[1] && !process->writeMemory(args[1], &info.pid, sizeof(info.pid))) code = -EFAULT;
                    if (!code && args[2] && !process->writeMemory(args[2], &info.uniqueID, sizeof(info.uniqueID))) code = -EFAULT;
                }
            }
        }
    }
    _sendReply(0, -code);
};

void DarlingServer::Call::VchrootPath::processCall() {
	int code = 0;
	size_t fullLength = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			if (_body.buffer_size > 0) {
				auto tmpstr = process->vchrootPath().substr(0, _body.buffer_size - 1);
				auto len = std::min(tmpstr.length() + 1, _body.buffer_size);

				fullLength = process->vchrootPath().length();

				if (!process->writeMemory(_body.buffer, tmpstr.c_str(), len, &code)) {
					// writeMemory returns a positive error code, but we want a negative one
					code = -code;
				}
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, fullLength);
};

void DarlingServer::Call::TaskSelfTrap::processCall() {
	const auto taskSelfPort = dtape_task_self_trap();
	_sendReply(0, taskSelfPort);
};

void DarlingServer::Call::HostSelfTrap::processCall() {
	const auto hostSelfPort = dtape_host_self_trap();
	_sendReply(0, hostSelfPort);
};

void DarlingServer::Call::ThreadSelfTrap::processCall() {
	const auto threadSelfPort = dtape_thread_self_trap();
	_sendReply(0, threadSelfPort);
};

void DarlingServer::Call::MachReplyPort::processCall() {
	const auto machReplyPort = dtape_mach_reply_port();
	_sendReply(0, machReplyPort);
};

void DarlingServer::Call::Kprintf::processCall() {
	static auto kprintfLog = Log("kprintf");
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			char* tmp = (char*)malloc(_body.string_length + 1);

			if (tmp) {
				if (process->readMemory(_body.string, tmp, _body.string_length, &code)) {
					size_t len = _body.string_length;

					// strip trailing whitespace
					while (len > 0 && isspace(tmp[len - 1])) {
						--len;
					}
					tmp[len] = '\0';

					kprintfLog.info() << tmp << kprintfLog.endLog;
				} else {
					// readMemory returns a positive error code, but we want a negative one
					code = -code;
				}

				free(tmp);
			} else {
				code = -ENOMEM;
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::StartedSuspended::processCall() {
	int code = 0;
	bool suspended = false;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			suspended = process->startSuspended();
			process->setStartSuspended(false);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, suspended);
};

void DarlingServer::Call::GetTracer::processCall() {
	int code = 0;
	int32_t tracer = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			if (auto tracerProcess = process->tracerProcess()) {
				tracer = tracerProcess->nsid();
			} else {
				// leave `tracer` as 0
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, tracer);
};

void DarlingServer::Call::Uidgid::processCall() {
	int code = 0;
	int uid = -1;
	int gid = -1;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			// HACK
			// we shouldn't need to access _dtapeTask; Process should provide a method for this (but it doesn't yet because i'm not sure how to make that API feel at-home in C++)
			dtape_task_uidgid(process->_dtapeTask, _body.new_uid, _body.new_gid, &uid, &gid);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, uid, gid);
};

void DarlingServer::Call::SetThreadHandles::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		thread->setThreadHandles(_body.pthread_handle, _body.dispatch_qaddr);
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::Vchroot::processCall() {
	int code = 0;

	// TODO: wrap all `processCall` calls in try-catch like this
	try {
		if (auto thread = _thread.lock()) {
			if (auto process = thread->process()) {
				process->setVchrootDirectory(std::make_shared<FD>(_body.directory_fd));
				_body.directory_fd = -1;
			} else {
				code = -ESRCH;
			}
		} else {
			code = -ESRCH;
		}
	} catch (std::system_error err) {
		code = -err.code().value();
	} catch (...) {
		code = std::numeric_limits<int>::min();
	}

	_sendReply(code);
};

void DarlingServer::Call::MldrPath::processCall() {
	int code = 0;
	uint64_t fullLength = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			auto tmpstr = std::string(Config::defaultMldrPath).substr(0, _body.buffer_size - 1);
			auto len = std::min(tmpstr.length() + 1, _body.buffer_size);

			fullLength = process->vchrootPath().length();

			if (!process->writeMemory(_body.buffer, tmpstr.c_str(), len, &code)) {
				// writeMemory returns a positive error code, but we want a negative one
				code = -code;
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, fullLength);
};

void DarlingServer::Call::ThreadGetSpecialReplyPort::processCall() {
	_sendReply(0, dtape_thread_get_special_reply_port());
};

void DarlingServer::Call::MkTimerCreate::processCall() {
	_sendReply(0, dtape_mk_timer_create());
};

void DarlingServer::Call::PthreadKill::processCall() {
	int code = 0;

	if (auto targetThread = Thread::threadForPort(_body.thread_port)) {
		try {
			targetThread->sendSignal(_body.signal);
		} catch (std::system_error e) {
			code = -e.code().value();
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::PthreadCanceled::processCall() {
	int code = 0;

	callLog.warning() << "TODO: " << __PRETTY_FUNCTION__ << callLog.endLog;
	code = -ENOSYS;

	_sendReply(code);
};

void DarlingServer::Call::PthreadMarkcancel::processCall() {
	int code = 0;

	if (auto targetThread = Thread::threadForPort(_body.thread_port)) {
		callLog.warning() << "TODO: " << __PRETTY_FUNCTION__ << callLog.endLog;
		code = -ENOSYS;
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::KqchanMachPortOpen::processCall() {
	int code = 0;
	int socket = -1;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			auto kqchan = std::make_shared<Kqchan::MachPort>(process, _body.port_name, _body.receive_buffer, _body.receive_buffer_size, _body.saved_filter_flags);

			try {
				socket = kqchan->setup();
			} catch (std::system_error e) {
				code = -e.code().value();
			} catch (...) {
				// just report that we couldn't find the port
				code = -ESRCH;
			}

			process->registerKqchan(kqchan);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, socket);
};

void DarlingServer::Call::KqchanProcOpen::processCall() {
	int code = 0;
	int socket = -1;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			auto kqchan = std::make_shared<Kqchan::Process>(process, _body.pid, _body.flags);

			try {
				socket = kqchan->setup();
			} catch (std::system_error e) {
				code = -e.code().value();
			} catch (...) {
				// just report that we couldn't find the process
				code = -ESRCH;
			}

			process->registerKqchan(kqchan);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, socket);
};

void DarlingServer::Call::ForkWaitForChild::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			process->waitForChildAfterFork();
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::Sigprocess::processCall() {
	int code = 0;
	int newBSDSignal = 0;

	if (auto thread = _thread.lock()) {
		try {
			thread->processSignal(_body.bsd_signal_number, _body.linux_signal_number, _body.code, _body.signal_address, _body.thread_state, _body.float_state);
			newBSDSignal = thread->pendingSignal();
		} catch (std::system_error e) {
			code = -e.code().value();
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, newBSDSignal);
};

void DarlingServer::Call::TaskIs64Bit::processCall() {
	int code = 0;
	bool is64Bit = false;

	if (auto maybeTargetProcess = processRegistry().lookupEntryByNSID(_body.id)) {
		auto targetProcess = *maybeTargetProcess;
		is64Bit = targetProcess->is64Bit();
	} else {
		code = -ESRCH;
	}

	_sendReply(code, is64Bit);
};

void DarlingServer::Call::InterruptEnter::processCall() {
	Thread::_handleInterruptEnterForCurrentThread();

	_sendReply(0);
};

void DarlingServer::Call::InterruptExit::processCall() {
	auto thread = _thread.lock();

	dtape_thread_sigexc_exit(thread->_dtapeThread);

	_sendReply(0);

	{
		std::unique_lock lock(thread->_rwlock);

		auto tmp = std::move(thread->_interrupts.top());

		thread->_interrupts.pop();

		if (tmp.savedReply) {
			callLog.debug() << *thread << ": Going to send saved reply" << callLog.endLog;
			Server::sharedInstance().sendMessage(std::move(*tmp.savedReply));
			tmp.savedReply = std::nullopt;
		}
	}
};

void DarlingServer::Call::RegisterSimulatorDyldSignature::processCall() {
    int result = -ESRCH;
    auto thread = _thread.lock();
    auto process = thread ? thread->process() : nullptr;
    if (process) {
        struct Signatures { uint64_t fileStart, blobStart, blobSize; } input{};
        uint64_t covered = 0;
        if (!process->is64Bit()) result = -ENOTSUP;
        else if (!process->readMemory(_body.signatures, &input, sizeof(input))) result = -EFAULT;
        else {
            std::string reason;
            result = -FileSignatures::registerSimulatorDyld(_body.fd, input.fileStart,
                input.blobStart, input.blobSize, covered, &reason);
            if (!result && !process->writeMemory(_body.signatures, &covered, sizeof(covered))) result = -EFAULT;
            if (getenv("DARLING_TRACE_FILE_SIGNATURES"))
                callLog.warning() << "simulator dyld signature: " << reason << "; result=" << result
                    << "; covered=" << covered << callLog.endLog;
        }
    }
    _sendReply(result);
}

void DarlingServer::Call::RegisterDylibSignature::processCall() {
    int result = -ESRCH;
    auto thread = _thread.lock();auto process = thread ? thread->process() : nullptr;
    if (process) {
        struct Signatures { uint64_t fileStart, blobStart, blobSize; } input{};
        uint64_t covered = 0;
        if (!process->is64Bit()) result = -ENOTSUP;
        else if (!process->readMemory(_body.signatures, &input, sizeof(input))) result = -EFAULT;
        else {
            result = -FileSignatures::registerEmbeddedFile(_body.fd,input.fileStart,input.blobStart,input.blobSize,covered);
            if (!result && !process->writeMemory(_body.signatures,&covered,sizeof(covered))) result = -EFAULT;
        }
    }
    _sendReply(result);
}

void DarlingServer::Call::FseventsOpen::processCall() {
    int result=-ESRCH;
    if (auto thread=_thread.lock()) if (auto process=thread->process()) {
        // This initial backend covers the actual virtual-root tree. External
        // SystemRoot aliases need additional roots before general CI promotion.
        try { result=FSEvents::openDevice({{process->vchrootPath(),"/"}},_body.flags); }
        catch (const std::bad_alloc&) { result=-ENOMEM; }
        catch (...) { result=-EIO; }
    }
    _sendReply(result<0?result:0,result<0?-1:result);
}

void DarlingServer::Call::FseventsIoctl::processCall() {
    int result=-ESRCH,output=-1;
    auto thread=_thread.lock();auto process=thread?thread->process():nullptr;
    if (process) {
        try {
            if (!FSEvents::isDevice(_body.fd)) result=-ENOTTY;
            else switch (_body.command) {
                case 0x80187301: { // FSEVENTS_CLONE, x86_64 24-byte structure
                    struct Clone { uint64_t actions;int32_t count,depth;uint64_t output; } args{};
                    if (!process->readMemory(_body.argument,&args,sizeof args)) { result=-EFAULT;break; }
                    if (args.count<1 || args.count>64 || args.depth<1 || args.depth>65536) { result=-EINVAL;break; }
                    std::vector<int8_t> actions(args.count);
                    if (!process->readMemory(args.actions,actions.data(),actions.size())) { result=-EFAULT;break; }
                    result=FSEvents::cloneDevice(_body.fd,actions,args.depth);
                    if (result>=0) { output=result;result=0; }
                    break;
                }
                case 0x800c7364: { // packed FSEVENTS_DEVICE_FILTER (exclusion list)
                    uint8_t bytes[12];uint32_t count;uint64_t address;
                    if (!process->readMemory(_body.argument,bytes,sizeof bytes)) { result=-EFAULT;break; }
                    std::memcpy(&count,bytes,4);std::memcpy(&address,bytes+4,8);
                    if (count>256) { result=-EINVAL;break; }
                    std::vector<uint32_t> devices(count);
                    if (count && !process->readMemory(address,devices.data(),count*4)) { result=-EFAULT;break; }
                    result=FSEvents::filterDevices(_body.fd,devices);break;
                }
                case 0x20007365: result=FSEvents::setCompact(_body.fd);break;
                case 0x20007366: result=FSEvents::setExtended(_body.fd);break;
                case 0x40087367: { // shared observed-event high-water mark
                    uint64_t value=0;
                    result=FSEvents::journalCurrent(_body.fd,Server::sharedInstance().prefix(),value);
                    if(!result&&!process->writeMemory(_body.argument,&value,sizeof value))result=-EFAULT;
                    break;
                }
                case 0x80107370: { // root opened through the client's actual vchroot
                    struct Root {uint64_t path;uint32_t length;int32_t descriptor;} args{};
                    if(!process->readMemory(_body.argument,&args,sizeof args)){result=-EFAULT;break;}
                    if(args.length<2||args.length>16384||args.descriptor<0){result=-EINVAL;break;}
                    std::string guest(args.length,'\0');
                    if(!process->readMemory(args.path,guest.data(),guest.size())){result=-EFAULT;break;}
                    if(guest.front()!='/'||guest.back()!='\0'||guest.find('\0')!=guest.size()-1){result=-EINVAL;break;}
                    guest.pop_back();
                    auto link="/proc/"+std::to_string(process->id())+"/fd/"+std::to_string(args.descriptor);
                    int directory=open(link.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC);
                    if(directory<0){result=-errno;break;}
                    std::vector<char> host(16384);auto name="/proc/self/fd/"+std::to_string(directory);
                    auto length=readlink(name.c_str(),host.data(),host.size()-1);int saved=errno;close(directory);
                    if(length<0){result=-saved;break;}
                    host[length]=0;
                    result=FSEvents::journalAddRoot(_body.fd,host.data(),guest);break;
                }
                case 0x80107371: {
                    struct Start {uint64_t since;uint32_t flags,reserved;} args{};
                    if(!process->readMemory(_body.argument,&args,sizeof args)){result=-EFAULT;break;}
                    if(args.reserved){result=-EINVAL;break;}
                    result=FSEvents::journalBegin(_body.fd,Server::sharedInstance().prefix(),args.since,args.flags);break;
                }
                case 0x40087372: {
                    uint64_t ticket=0;result=FSEvents::journalBarrier(_body.fd,ticket);
                    if(!result&&!process->writeMemory(_body.argument,&ticket,sizeof ticket))result=-EFAULT;
                    break;
                }
                default: result=-ENOTTY;break;
            }
        } catch (const std::bad_alloc&) { result=-ENOMEM; }
        catch (...) { result=-EIO; }
    }
    _sendReply(result,output);
}

void DarlingServer::Call::ConsoleOpen::processCall() {
	static Log consoleLog("console");

	int code = 0;
	int sockets[2] = { -1, -1 };

	// we don't really need bidirectional communication, so a pipe would suffice,
	// except that when you set O_NONBLOCK on one side of a pipe, it is set for both.

	if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sockets) < 0) {
		int err = errno;
		callLog.warning() << __PRETTY_FUNCTION__ << ": socketpair failed with " << err << callLog.endLog;

		// just report EMFILE for the peer
		code = EMFILE;
	} else {
		// make our side non-blocking
		int flags = fcntl(sockets[0], F_GETFL);
		if (flags < 0) {
			code = -errno;
		} else {
			flags |= O_NONBLOCK;
			if (fcntl(sockets[0], F_SETFL, flags) < 0) {
				code = -errno;
			} else {
				// now monitor it
				auto fd = std::make_shared<FD>(sockets[0]);
				std::weak_ptr<Process> weakProcess;

				if (auto thread = _thread.lock()) {
					if (auto process = thread->process()) {
						weakProcess = process;
					}
				}

				Server::sharedInstance().addMonitor(std::make_shared<Monitor>(fd, Monitor::Event::Readable | Monitor::Event::HangUp, false, false, [fd, weakProcess](std::shared_ptr<Monitor> monitor, Monitor::Event events) {
					auto proc = weakProcess.lock();

					if (!proc || static_cast<uint64_t>(events & Monitor::Event::HangUp) != 0) {
						Server::sharedInstance().removeMonitor(monitor);
						return;
					}

					if (static_cast<uint64_t>(events & Monitor::Event::Readable) != 0) {
						std::stringstream data;
						while (true) {
							char buf[128];
							auto count = read(fd->fd(), buf, sizeof(buf) - 1);
							if (count <= 0) {
								break;
							}
							buf[count] = '\0';
							data << buf;
						}
						consoleLog.info() << *proc << ": " << data.rdbuf();
					}
				}));
			}
		}
	}

	if (code != 0) {
		if (sockets[0] >= 0) {
			close(sockets[0]);
			sockets[0] = -1;
		}
		if (sockets[1] >= 0) {
			close(sockets[1]);
			sockets[1] = -1;
		}
	}
	_sendReply(code, sockets[1]);
};

void DarlingServer::Call::SetDyldInfo::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			dtape_task_set_dyld_info(process->_dtapeTask, _body.address, _body.length);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::StopAfterExec::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			process->setStartSuspended(true);
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::SetTracer::processCall() {
	int code = 0;
	std::shared_ptr<Process> targetProcess = nullptr;
	std::shared_ptr<Process> tracerProcess = nullptr;

	if (_body.target == 0) {
		if (auto thread = _thread.lock()) {
			targetProcess = thread->process();
		}
	} else {
		if (auto maybeTargetProcess = processRegistry().lookupEntryByNSID(_body.target)) {
			targetProcess = *maybeTargetProcess;
		}
	}

	if (targetProcess) {
		if (_body.tracer == 0) {
			// leave tracer process as nullptr
		} else {
			if (auto maybeTracerProcess = processRegistry().lookupEntryByNSID(_body.tracer)) {
				tracerProcess = *maybeTracerProcess;
			} else {
				// intentionally not negated because this is not an internal error;
				// this is a perfectly valid case
				code = ESRCH;
			}
		}

		if (code == 0) {
			if (!targetProcess->setTracerProcess(tracerProcess)) {
				// again, not negated because this isn't an internal error;
				// simply indicates there was already a tracer set for the target
				code = EPERM;
			}
		}
	} else {
		// ditto from before
		code = ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::TidForThread::processCall() {
	int code = 0;
	int32_t tid = 0;

	if (auto thread = Thread::threadForPort(_body.thread)) {
		tid = thread->nsid();
	} else {
		// might be user error (e.g. invalid port number or dead thread), so don't negate it
		code = ESRCH;
	}

	_sendReply(code, tid);
};

void DarlingServer::Call::PtraceSigexc::processCall() {
	int code = 0;

	if (auto maybeProcess = processRegistry().lookupEntryByNSID(_body.target)) {
		auto process = *maybeProcess;

		dtape_task_set_sigexc_enabled(process->_dtapeTask, _body.enabled);
		dtape_task_try_resume(process->_dtapeTask);
	} else {
		// not negated because this isn't an internal error
		code = ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::PtraceThupdate::processCall() {
	int code = 0;

	if (auto maybeThread = threadRegistry().lookupEntryByNSID(_body.target)) {
		auto thread = *maybeThread;

		thread->setPendingSignal(_body.signum);
	} else {
		// not negated because this isn't an internal error
		code = ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::ThreadSuspended::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		thread->waitWhileUserSuspended(_body.thread_state, _body.float_state);
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::S2CPerform::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		dtape_semaphore_up(thread->_s2cInterruptEnterSemaphore);
		dtape_semaphore_down_simple(thread->_s2cInterruptExitSemaphore);
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
};

void DarlingServer::Call::SetExecutablePath::processCall() {
	int code = 0;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			std::string tmpstr;
			tmpstr.resize(_body.buffer_size);
			if (!process->readMemory((uintptr_t)_body.buffer, tmpstr.data(), _body.buffer_size, &code)) {
				code = -code;
			} else {
				process->setExecutablePath(tmpstr.c_str());
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code);
}

void DarlingServer::Call::GetExecutablePath::processCall() {
	int code = 0;
	uint64_t fullLength;

	if (auto callingThread = _thread.lock()) {
		if (auto callingProcess = callingThread->process()) {
			if (auto maybeTargetProcess = processRegistry().lookupEntryByNSID(_body.pid)) {
				auto targetProcess = *maybeTargetProcess;
				auto path = targetProcess->executablePath();
				auto len = std::min(path.length() + 1, _body.buffer_size);
				if (!callingProcess->writeMemory((uintptr_t)_body.buffer, path.c_str(), len, &code)) {
					code = -code;
				}
				fullLength = path.length();
			} else {
				// not negated because this is an acceptable case.
				// e.g. the target process may have died before the call was processed.
				code = ESRCH;
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, fullLength);
}

void DarlingServer::Call::Groups::processCall() {
	int code = 0;
	std::vector<uint32_t> oldGroups;

	if (auto thread = _thread.lock()) {
		if (auto process = thread->process()) {
			oldGroups = process->groups();

			if (_body.new_groups != 0 && _body.new_group_count > 0) {
				std::vector<uint32_t> newGroups;
				newGroups.resize(_body.new_group_count);

				if (!process->readMemory((uintptr_t)_body.new_groups, newGroups.data(), newGroups.size() * sizeof(uint32_t), &code)) {
					code = -code;
				} else {
					process->setGroups(newGroups);
				}
			}

			if (code == 0 && _body.old_groups != 0 && _body.old_group_space > 0) {
				auto len = std::min(oldGroups.size(), _body.old_group_space) * sizeof(uint32_t);
				if (!process->writeMemory((uintptr_t)_body.old_groups, oldGroups.data(), len, &code)) {
					code = -code;
				}
			}
		} else {
			code = -ESRCH;
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, oldGroups.size());
};

void DarlingServer::Call::DebugListProcesses::processCall() {
	int code = 0;
	auto processes = processRegistry().copyEntries();
	int pipes[2] = {-1, -1};

	code = pipe(pipes);
	if (code == 0) {
		for (const auto& process: processes) {
			dserver_debug_process_t debugProcess;
			debugProcess.pid = process->nsid();
			debugProcess.port_count = dtape_debug_task_port_count(process->_dtapeTask);
			write(pipes[1], &debugProcess, sizeof(debugProcess));
		}

		close(pipes[1]);
	}

	_sendReply(code, processes.size(), pipes[0]);
};

void DarlingServer::Call::DebugListPorts::processCall() {
	int code = 0;
	uint64_t portCount = 0;
	int pipes[2] = {-1, -1};

	if (auto maybeProcess = processRegistry().lookupEntryByNSID(_body.process)) {
		auto process = *maybeProcess;

		code = pipe(pipes);
		if (code == 0) {
			portCount = dtape_debug_task_list_ports(process->_dtapeTask, [](void* context, const dtape_debug_port_t* port) {
				int& writeFD = *(int*)context;
				dserver_debug_port_t debugPort;

				debugPort.port_name = port->name;
				debugPort.rights = port->rights;
				debugPort.refs = port->refs;
				debugPort.messages = port->messages;

				write(writeFD, &debugPort, sizeof(debugPort));

				return true;
			}, &pipes[1]);
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, portCount, pipes[0]);
};

void DarlingServer::Call::DebugListMembers::processCall() {
	int code = 0;
	uint64_t portCount = 0;
	int pipes[2] = {-1, -1};

	if (auto maybeProcess = processRegistry().lookupEntryByNSID(_body.process)) {
		auto process = *maybeProcess;

		code = pipe(pipes);
		if (code == 0) {
			portCount = dtape_debug_portset_list_members(process->_dtapeTask, _body.portset, [](void* context, const dtape_debug_port_t* port) {
				int& writeFD = *(int*)context;
				dserver_debug_port_t debugPort;

				debugPort.port_name = port->name;
				debugPort.rights = port->rights;
				debugPort.refs = port->refs;
				debugPort.messages = port->messages;

				write(writeFD, &debugPort, sizeof(debugPort));

				return true;
			}, &pipes[1]);
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, portCount, pipes[0]);
};

void DarlingServer::Call::DebugListMessages::processCall() {
	int code = 0;
	uint64_t portCount = 0;
	int pipes[2] = {-1, -1};

	if (auto maybeProcess = processRegistry().lookupEntryByNSID(_body.process)) {
		auto process = *maybeProcess;

		code = pipe(pipes);
		if (code == 0) {
			portCount = dtape_debug_port_list_messages(process->_dtapeTask, _body.port, [](void* context, const dtape_debug_message_t* port) {
				int& writeFD = *(int*)context;
				dserver_debug_message_t debugMessage;

				debugMessage.sender = port->sender;
				debugMessage.size = port->size;

				write(writeFD, &debugMessage, sizeof(debugMessage));

				return true;
			}, &pipes[1]);
		}
	} else {
		code = -ESRCH;
	}

	_sendReply(code, portCount, pipes[0]);
};

DSERVER_CLASS_SOURCE_DEFS;

void DarlingServer::Call::AuditInfo::processCall() {
    int code=-ESRCH;
    auto thread=_thread.lock();
    auto process=thread ? thread->process() : nullptr;
    if (process) {
        // The kernel client cannot nominate credentials through this RPC.
        // Read the current effective UID from the authenticated process PID.
        std::ifstream status("/proc/"+std::to_string(process->_pid)+"/status");
        std::string line; uint32_t ruid=UINT32_MAX,euid=UINT32_MAX;
        while (std::getline(status,line)) {
            if (line.compare(0,4,"Uid:")==0) {
                std::istringstream fields(line.substr(4)); fields>>ruid>>euid; break;
            }
        }
        if (euid!=UINT32_MAX) {
            darling_audit_info_t info{};
            size_t count=std::min<size_t>(_body.length,sizeof(info));
            if (_body.operation==0) {
                {
                    std::shared_lock lock(process->_rwlock);
                    info=process->_auditSession->info;
                    info.mask_success=euid ? UINT32_MAX : process->_auditMaskSuccess;
                    info.mask_failure=euid ? UINT32_MAX : process->_auditMaskFailure;
                }
                code=(!count || process->writeMemory(_body.buffer,&info,count)) ? 0 : -EFAULT;
            } else if (_body.operation==1) {
                if (count && !process->readMemory(_body.buffer,&info,count)) code=-EFAULT;
                else if (euid) code=-EPERM;
                else if (info.terminal_type!=4 && info.terminal_type!=16) code=-EINVAL;
                // Only a headless session is supported. Do not advertise UI,
                // TTY or remote-login attributes that this backend can't grant.
                else if (info.flags) code=-EINVAL;
                else {
                    std::unique_lock lock(process->_rwlock);
                    auto old=process->_auditSession;
                    if (info.asid==0 || info.asid==UINT32_MAX) {
                        try { process->_auditSession=AuditSession::create(info); code=0; }
                        catch (const std::system_error& e) { code=-e.code().value(); }
                    } else if (info.asid!=old->info.asid) code=-ENOTSUP;
                    else if (info.auid!=old->info.auid || info.flags!=old->info.flags ||
                             info.terminal_type!=old->info.terminal_type ||
                             info.terminal_port!=old->info.terminal_port ||
                             memcmp(info.terminal_address,old->info.terminal_address,sizeof(info.terminal_address))) code=-EINVAL;
                    else code=0;
                    if (!code) {
                        process->_auditMaskSuccess=info.mask_success;
                        process->_auditMaskFailure=info.mask_failure;
                        dtape_task_set_audit_identity(process->_dtapeTask,process->_auditSession->info.auid,process->_auditSession->info.asid);
                    }
                }
            } else code=-EINVAL;
        }
    }
    _sendReply(code);
}
